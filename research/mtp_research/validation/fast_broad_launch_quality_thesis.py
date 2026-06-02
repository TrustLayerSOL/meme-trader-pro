"""Descriptive T009 fast + broad early launch quality thesis cycle."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


THESIS_ID = "T009"
THESIS_NAME = "FAST + BROAD EARLY LAUNCH QUALITY"
ALLOWED_CLASSIFICATIONS = {"descriptive_signal_present", "weak_signal", "no_signal", "data_limited"}
REPORT_JSON = "T009_fast_broad_launch_quality_summary.json"
REPORT_MD = "T009_fast_broad_launch_quality_summary.md"
PRIMARY_AGE = 60
HOLDER_NEAREST_AGE = 60
CONCENTRATION_FIELDS = ["top_holder_share", "top_10_holder_share", "creator_holder_share"]
ENTITY_FIELDS = [
    "repeated_actor_overlap_proxy",
    "repeated_buyer_overlap_proxy",
    "synchronized_participation_proxy",
    "circularity_proxy",
    "churn_proxy",
    "creator_linked_share_proxy",
]
AUDIT_FIELDS = [
    "valuation_proxy_usd_1m",
    "event_count_60s",
    "buy_count_60s",
    "sell_count_60s",
    "buy_share_60s",
    "active_wallets_60s",
    "unique_actors_60s",
    "buys_per_actor_60s",
    "events_per_actor_60s",
    "holder_count_60s_or_nearest",
    "top_holder_share_60s_or_nearest",
    "top_10_holder_share_60s_or_nearest",
    "creator_holder_share_60s_or_nearest",
    *ENTITY_FIELDS,
    "creator_prior_migration_or_graduation_count",
]


def build_t009_fast_broad_launch_quality_report(
    *,
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    holder_state_snapshots_path: Path | str | None = None,
    entity_proxy_path: Path | str | None = None,
    migration_labels_path: Path | str | None = None,
    t005_summary_path: Path | str | None = None,
    dataset_scope: str = "all_collected",
) -> dict[str, Any]:
    snapshots = _read_jsonl(snapshots_path)
    outcomes_by_mint = {_mint(row): row for row in _read_jsonl(outcomes_path)}
    holder_by_mint = _holder_by_mint(_read_jsonl(holder_state_snapshots_path)) if holder_state_snapshots_path else {}
    entity_by_mint = {_mint(row): row for row in _read_jsonl(entity_proxy_path)} if entity_proxy_path else {}
    migration_context = _migration_context(_read_jsonl(migration_labels_path)) if migration_labels_path else {}
    t005_summary = _read_json(t005_summary_path) if t005_summary_path else None

    rows = _build_launch_rows(
        snapshots=snapshots,
        outcomes_by_mint=outcomes_by_mint,
        holder_by_mint=holder_by_mint,
        entity_by_mint=entity_by_mint,
        migration_context=migration_context,
    )
    rows.sort(key=lambda row: (row.get("launch_ts") or 0, row["token_mint"]))
    selected_features, feature_warnings = _select_primary_features(rows)
    _assign_speed_breadth_groups(rows, selected_features)
    _assign_concentration_groups(rows)

    field_audit = _field_coverage_audit(rows)
    interaction_summary = _interaction_summary(rows)
    main_comparisons = _main_comparisons(interaction_summary, rows)
    concentration_overlay = _concentration_overlay(rows)
    robustness = _robustness_checks(rows)
    t005_comparison = _compare_to_t005(main_comparisons, t005_summary)
    warning_flags = _warning_flags(
        rows=rows,
        field_audit=field_audit,
        feature_warnings=feature_warnings,
        holder_state_snapshots_path=holder_state_snapshots_path,
        entity_proxy_path=entity_proxy_path,
        migration_labels_path=migration_labels_path,
    )
    classification = _classify(rows, interaction_summary, main_comparisons, robustness, warning_flags)
    return {
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "research_question": (
            "Among launches with strong early acceleration, do broad/distributed launches perform "
            "better than fast/concentrated launches?"
        ),
        "hypothesis": "Fast early growth is more meaningful when paired with broad, distributed participation.",
        "dataset": {
            "dataset_scope": dataset_scope,
            "snapshots_path": str(snapshots_path),
            "outcomes_path": str(outcomes_path),
            "holder_state_snapshots_path": str(holder_state_snapshots_path) if holder_state_snapshots_path else None,
            "entity_proxy_path": str(entity_proxy_path) if entity_proxy_path else None,
            "migration_labels_path": str(migration_labels_path) if migration_labels_path else None,
            "launch_count": len(rows),
            "snapshot_count": len(snapshots),
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "methodology": {
            "speed_bucket_method": "deterministic_tercile_quantile_bucket",
            "breadth_bucket_method": "deterministic_tercile_quantile_bucket",
            "concentration_bucket_method": "deterministic_tercile_quantile_bucket_with_available_sidecar_rows_only",
            "interaction_groups": [
                "fast_and_broad",
                "fast_and_narrow",
                "slow_and_broad",
                "slow_and_narrow",
                "middle_or_other",
            ],
            "classification_options": sorted(ALLOWED_CLASSIFICATIONS),
        },
        "methodology_flags": [
            "research_only",
            "descriptive_historical_thesis",
            "no_thesis_promotion",
            "no_backtest",
            "no_walk_forward_validation",
            "no_trading_rules",
            "no_profitability_claims",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_future_leakage",
            "fdv_proxy_not_true_market_cap",
        ],
        "selected_features": selected_features,
        "field_coverage_audit": field_audit,
        "sample_counts": {"launch_count": len(rows), "token_count": len({row["token_mint"] for row in rows})},
        "interaction_groups": interaction_summary,
        "secondary_concentration_overlay": concentration_overlay,
        "main_comparisons": main_comparisons,
        "robustness_checks": robustness,
        "t005_baseline_comparison": t005_comparison,
        "launch_rows": rows,
        "final_classification": classification,
        "warning_flags": warning_flags,
        "limitations": _limitations(warning_flags),
        "chronological_robustness_recommended": classification in {"descriptive_signal_present", "weak_signal"},
        "next_recommendation": _next_recommendation(classification),
        "reproducible_command": _reproducible_command(
            snapshots_path,
            outcomes_path,
            holder_state_snapshots_path,
            entity_proxy_path,
            migration_labels_path,
            t005_summary_path,
            dataset_scope,
        ),
    }


def write_t009_report_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / REPORT_JSON
    markdown_path = output / REPORT_MD
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": markdown_path, "status_path": status}


def _build_launch_rows(
    *,
    snapshots: list[dict[str, Any]],
    outcomes_by_mint: dict[str, dict[str, Any]],
    holder_by_mint: dict[str, list[dict[str, Any]]],
    entity_by_mint: dict[str, dict[str, Any]],
    migration_context: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped = _group_by_mint(snapshots)
    rows = []
    for mint, mint_snapshots in sorted(grouped.items()):
        by_age = {int(row.get("launch_age_seconds", 0)): row for row in mint_snapshots}
        primary = by_age.get(PRIMARY_AGE) or min(mint_snapshots, key=lambda row: abs(int(row.get("launch_age_seconds", 0)) - PRIMARY_AGE))
        holder = _nearest_holder(holder_by_mint.get(mint, []), HOLDER_NEAREST_AGE)
        entity = entity_by_mint.get(mint, {})
        outcome = outcomes_by_mint.get(mint, {})
        migration = migration_context.get(mint, {})
        features = _features(primary, holder, entity, migration)
        rows.append(
            {
                "launch_id": _first_present(primary.get("launch_id"), outcome.get("launch_id"), entity.get("launch_id")),
                "token_mint": mint,
                "mint": mint,
                "launch_ts": _int_or_none(_first_present(primary.get("launch_ts"), outcome.get("launch_ts"))),
                "creator": _creator(primary, outcome, entity, migration),
                "features": features,
                "outcomes": _outcomes(mint_snapshots, outcome, migration),
                "metadata_json": {
                    "primary_snapshot_age_seconds": primary.get("launch_age_seconds"),
                    "holder_state_snapshot_age_seconds": holder.get("snapshot_age_seconds") if holder else None,
                    "holder_state_confidence": holder.get("holder_snapshot_confidence") if holder else None,
                    "entity_proxy_confidence": entity.get("proxy_confidence"),
                    "migration_context_available": bool(migration),
                },
            }
        )
    return rows


def _features(
    snapshot: dict[str, Any],
    holder: dict[str, Any] | None,
    entity: dict[str, Any],
    migration: dict[str, Any],
) -> dict[str, Any]:
    buys = _float_or_none(snapshot.get("buy_count"))
    sells = _float_or_none(snapshot.get("sell_count"))
    events = _event_count(snapshot)
    actors = _float_or_none(snapshot.get("unique_actors"))
    active_wallets = _float_or_none(snapshot.get("active_wallets"))
    return {
        "valuation_proxy_usd_1m": _float_or_none(snapshot.get("valuation_proxy_usd"))
        if snapshot.get("valuation_proxy_available") is not False
        else None,
        "event_count_60s": events,
        "buy_count_60s": buys,
        "sell_count_60s": sells,
        "buy_share_60s": _ratio(buys, events),
        "active_wallets_60s": active_wallets,
        "unique_actors_60s": actors,
        "buys_per_actor_60s": _ratio(buys, actors),
        "events_per_actor_60s": _ratio(events, actors),
        "holder_count_60s_or_nearest": _holder_value(holder, "holder_count"),
        "top_holder_share_60s_or_nearest": _holder_value(holder, "top_holder_share"),
        "top_10_holder_share_60s_or_nearest": _holder_value(holder, "top_10_holder_share"),
        "creator_holder_share_60s_or_nearest": _holder_value(holder, "creator_holder_share"),
        **{field: _float_or_none(entity.get(field)) for field in ENTITY_FIELDS},
        "creator_prior_migration_or_graduation_count": _float_or_none(
            migration.get("creator_prior_migration_or_graduation_count")
        ),
        "migration_or_graduation_observed": bool(migration.get("migration_or_graduation_observed")),
    }


def _outcomes(snapshots: list[dict[str, Any]], outcome: dict[str, Any], migration: dict[str, Any]) -> dict[str, Any]:
    runup = _nested_float(outcome, "runups", "max_runup_120m")
    drawdown = _nested_float(outcome, "drawdowns", "max_drawdown_120m")
    if runup is None or drawdown is None:
        values = [
            _float_or_none(row.get("valuation_proxy_usd"))
            for row in sorted(snapshots, key=lambda row: int(row.get("launch_age_seconds", 0)))
            if row.get("valuation_proxy_available") and _float_or_none(row.get("valuation_proxy_usd")) is not None
        ]
        values = [value for value in values if value is not None]
        if values and values[0] not in (None, 0):
            runup = (max(values) / values[0]) - 1 if runup is None else runup
            drawdown = (min(values) / values[0]) - 1 if drawdown is None else drawdown
    return {
        "fdv_proxy_runup_120m": runup,
        "fdv_proxy_drawdown_120m": drawdown,
        "price_available_120m": bool(outcome.get("price_available_120m") or outcome.get("has_price_at_120m")),
        "liquidity_proxy_available_120m": bool(
            outcome.get("has_liquidity_proxy_at_120m") or outcome.get("liquidity_survival_120m")
        ),
        "migration_or_graduation_observed": bool(migration.get("migration_or_graduation_observed")),
        "peak_fdv_proxy_outcome": _float_or_none(outcome.get("valuation_proxy_usd")),
        "true_market_cap_available": bool(outcome.get("true_market_cap_available") or outcome.get("market_cap_available")),
    }


def _select_primary_features(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    warnings = []
    if _coverage(rows, "valuation_proxy_usd_1m")["available_rows"] > 0:
        speed = "valuation_proxy_usd_1m"
    else:
        speed = "event_count_60s"
        warnings.append("primary_speed_fdv_unavailable_used_event_count_fallback")
    breadth = "active_wallets_60s" if _coverage(rows, "active_wallets_60s")["available_rows"] > 0 else "unique_actors_60s"
    concentration = [
        field
        for field in [
            "top_holder_share_60s_or_nearest",
            "top_10_holder_share_60s_or_nearest",
            "creator_holder_share_60s_or_nearest",
        ]
        if _coverage(rows, field)["available_rows"] > 0
    ]
    return {
        "speed_feature_used": speed,
        "breadth_feature_used": breadth,
        "concentration_fields_used": concentration,
        "speed_feature_reason": "first-minute FDV proxy available" if speed == "valuation_proxy_usd_1m" else "FDV proxy unavailable",
        "breadth_feature_reason": "active wallet breadth is available at 60s"
        if breadth == "active_wallets_60s"
        else "active wallets unavailable; unique actors fallback",
    }, warnings


def _assign_speed_breadth_groups(rows: list[dict[str, Any]], selected: dict[str, Any]) -> None:
    _assign_quantile_labels(rows, selected["speed_feature_used"], "speed_bucket")
    _assign_quantile_labels(
        rows,
        selected["breadth_feature_used"],
        "breadth_bucket",
        labels=("low_breadth", "medium_breadth", "high_breadth"),
    )
    for row in rows:
        speed = row.get("speed_bucket")
        breadth = row.get("breadth_bucket")
        if speed == "high_speed" and breadth == "high_breadth":
            group = "fast_and_broad"
        elif speed == "high_speed" and breadth == "low_breadth":
            group = "fast_and_narrow"
        elif speed == "low_speed" and breadth == "high_breadth":
            group = "slow_and_broad"
        elif speed == "low_speed" and breadth == "low_breadth":
            group = "slow_and_narrow"
        else:
            group = "middle_or_other"
        row["interaction_group"] = group


def _assign_concentration_groups(rows: list[dict[str, Any]]) -> None:
    candidates = [
        "top_holder_share_60s_or_nearest",
        "top_10_holder_share_60s_or_nearest",
        "creator_holder_share_60s_or_nearest",
        "creator_linked_share_proxy",
    ]
    best = max(candidates, key=lambda field: _coverage(rows, field)["available_rows"])
    _assign_quantile_labels(rows, best, "concentration_bucket", labels=("low_concentration", "medium_concentration", "high_concentration"))
    for row in rows:
        row["concentration_feature_used"] = best


def _assign_quantile_labels(
    rows: list[dict[str, Any]],
    feature: str,
    target: str,
    labels: tuple[str, str, str] = ("low_speed", "medium_speed", "high_speed"),
) -> None:
    usable = [(idx, _feature_value(row, feature)) for idx, row in enumerate(rows)]
    usable = [(idx, value) for idx, value in usable if value is not None]
    usable.sort(key=lambda item: (item[1], rows[item[0]].get("launch_ts") or 0, rows[item[0]]["token_mint"]))
    n = len(usable)
    for rank, (idx, _value) in enumerate(usable):
        if n == 0:
            label = None
        elif rank < n / 3:
            label = labels[0]
        elif rank < (2 * n) / 3:
            label = labels[1]
        else:
            label = labels[2]
        rows[idx][target] = label
    for row in rows:
        row.setdefault(target, None)


def _interaction_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups = defaultdict(list)
    for row in rows:
        groups[row.get("interaction_group") or "unassigned"].append(row)
    order = ["fast_and_broad", "fast_and_narrow", "slow_and_broad", "slow_and_narrow", "middle_or_other", "unassigned"]
    return {
        "counts": {group: len(groups.get(group, [])) for group in order if group in groups or group != "unassigned"},
        "outcome_tables": {group: _group_outcomes(groups.get(group, [])) for group in order if group in groups or group != "unassigned"},
    }


def _group_outcomes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    runups = [_outcome_value(row, "fdv_proxy_runup_120m") for row in rows]
    drawdowns = [_outcome_value(row, "fdv_proxy_drawdown_120m") for row in rows]
    runups = [value for value in runups if value is not None]
    drawdowns = [value for value in drawdowns if value is not None]
    return {
        "sample_count": len(rows),
        "token_count": len({row["token_mint"] for row in rows}),
        "median_fdv_proxy_runup_120m": _median_or_none(runups),
        "median_fdv_proxy_drawdown_120m": _median_or_none(drawdowns),
        "price_available_120m_rate": _rate(rows, "price_available_120m"),
        "liquidity_proxy_available_120m_rate": _rate(rows, "liquidity_proxy_available_120m"),
        "migration_or_graduation_observed_count": sum(
            1 for row in rows if row["outcomes"].get("migration_or_graduation_observed")
        ),
    }


def _main_comparisons(summary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    tables = summary["outcome_tables"]
    comparisons = {
        "fast_and_broad_vs_fast_and_narrow": _compare_groups(tables, "fast_and_broad", "fast_and_narrow"),
        "high_speed_high_breadth_vs_high_speed_low_breadth": _compare_groups(tables, "fast_and_broad", "fast_and_narrow"),
        "fast_and_broad_vs_all_other": _compare_row_sets(rows, "fast_and_broad", include=True),
        "fast_and_narrow_vs_all_other": _compare_row_sets(rows, "fast_and_narrow", include=True),
    }
    high_speed = [row for row in rows if row.get("speed_bucket") == "high_speed" and row.get("concentration_bucket")]
    low_conc = [row for row in high_speed if row.get("concentration_bucket") == "low_concentration"]
    high_conc = [row for row in high_speed if row.get("concentration_bucket") == "high_concentration"]
    comparisons["high_speed_low_concentration_vs_high_speed_high_concentration"] = {
        "left_group": "high_speed_low_concentration",
        "right_group": "high_speed_high_concentration",
        "left": _group_outcomes(low_conc),
        "right": _group_outcomes(high_conc),
        "median_runup_delta": _delta(_group_outcomes(low_conc), _group_outcomes(high_conc), "median_fdv_proxy_runup_120m"),
        "median_drawdown_delta": _delta(
            _group_outcomes(low_conc), _group_outcomes(high_conc), "median_fdv_proxy_drawdown_120m"
        ),
    }
    return comparisons


def _compare_groups(tables: dict[str, dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    left_table = tables.get(left, _group_outcomes([]))
    right_table = tables.get(right, _group_outcomes([]))
    return {
        "left_group": left,
        "right_group": right,
        "left": left_table,
        "right": right_table,
        "median_runup_delta": _delta(left_table, right_table, "median_fdv_proxy_runup_120m"),
        "median_drawdown_delta": _delta(left_table, right_table, "median_fdv_proxy_drawdown_120m"),
        "left_outperformed_descriptively": _outperformed(left_table, right_table),
    }


def _compare_row_sets(rows: list[dict[str, Any]], group: str, include: bool) -> dict[str, Any]:
    left = [row for row in rows if (row.get("interaction_group") == group) == include]
    right = [row for row in rows if (row.get("interaction_group") == group) != include]
    left_table = _group_outcomes(left)
    right_table = _group_outcomes(right)
    return {
        "left_group": group,
        "right_group": "all_other",
        "left": left_table,
        "right": right_table,
        "median_runup_delta": _delta(left_table, right_table, "median_fdv_proxy_runup_120m"),
        "median_drawdown_delta": _delta(left_table, right_table, "median_fdv_proxy_drawdown_120m"),
        "left_outperformed_descriptively": _outperformed(left_table, right_table),
    }


def _concentration_overlay(rows: list[dict[str, Any]]) -> dict[str, Any]:
    high_speed = [row for row in rows if row.get("speed_bucket") == "high_speed"]
    groups = defaultdict(list)
    for row in high_speed:
        if row.get("concentration_bucket"):
            groups[row["concentration_bucket"]].append(row)
    return {
        "concentration_feature_used": rows[0].get("concentration_feature_used") if rows else None,
        "high_speed_concentration_groups": {
            group: _group_outcomes(groups.get(group, []))
            for group in ["low_concentration", "medium_concentration", "high_concentration"]
        },
    }


def _robustness_checks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    runups = sorted([_outcome_value(row, "fdv_proxy_runup_120m") for row in rows if _outcome_value(row, "fdv_proxy_runup_120m") is not None])
    return {
        "exclude_top_1pct_fdv_proxy_runups": _trimmed_group_comparison(rows, runups, 0.99),
        "exclude_top_5pct_fdv_proxy_runups": _trimmed_group_comparison(rows, runups, 0.95),
        "chronological_halves": _chronological_halves(rows),
        "creator_dominance": _creator_dominance(rows),
        "t008_prior_migration_dominance": _t008_dominance(rows),
    }


def _trimmed_group_comparison(rows: list[dict[str, Any]], sorted_runups: list[float], pct: float) -> dict[str, Any]:
    if not sorted_runups:
        return {"usable": False, "reason": "no_fdv_proxy_runups"}
    cutoff = sorted_runups[max(0, min(len(sorted_runups) - 1, int(len(sorted_runups) * pct) - 1))]
    trimmed = [row for row in rows if (_outcome_value(row, "fdv_proxy_runup_120m") or 0) <= cutoff]
    summary = _interaction_summary(trimmed)
    return {
        "usable": True,
        "cutoff": cutoff,
        "remaining_launch_count": len(trimmed),
        "fast_and_broad_vs_fast_and_narrow": _compare_groups(
            summary["outcome_tables"], "fast_and_broad", "fast_and_narrow"
        ),
    }


def _chronological_halves(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row.get("launch_ts") or 0, row["token_mint"]))
    mid = len(ordered) // 2
    output = {}
    for label, subset in [("first_half", ordered[:mid]), ("second_half", ordered[mid:])]:
        summary = _interaction_summary(subset)
        output[label] = _compare_groups(summary["outcome_tables"], "fast_and_broad", "fast_and_narrow")
    return output


def _creator_dominance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fast_broad = [row for row in rows if row.get("interaction_group") == "fast_and_broad"]
    counts = Counter(row.get("creator") or "unknown" for row in fast_broad)
    total = len(fast_broad)
    top = counts.most_common(5)
    return {
        "fast_and_broad_launch_count": total,
        "top_creator_share": _safe_round(top[0][1] / total) if total and top else None,
        "top_creators": [{"creator": creator, "launch_count": count} for creator, count in top],
    }


def _t008_dominance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fast_broad = [row for row in rows if row.get("interaction_group") == "fast_and_broad"]
    with_prior = [
        row
        for row in fast_broad
        if (_feature_value(row, "creator_prior_migration_or_graduation_count") or 0) > 0
    ]
    return {
        "fast_and_broad_launch_count": len(fast_broad),
        "with_prior_migration_or_graduation_count": len(with_prior),
        "with_prior_migration_or_graduation_share": _pct(len(with_prior), len(fast_broad)),
    }


def _compare_to_t005(comparison: dict[str, Any], t005_summary: dict[str, Any] | None) -> dict[str, Any]:
    t009_delta = comparison["fast_and_broad_vs_fast_and_narrow"].get("median_runup_delta")
    result = {
        "t005_summary_available": bool(t005_summary),
        "t005_classification": t005_summary.get("final_classification") if t005_summary else None,
        "t009_fast_broad_runup_delta": t009_delta,
        "t009_provides_clearer_separation_than_t005_baseline": None,
        "comparison_note": "Qualitative descriptive comparison only; no validation or promotion is made.",
    }
    if not t005_summary or t009_delta is None:
        return result
    t005_delta = _max_t005_bucket_spread(t005_summary)
    result["t005_max_bucket_runup_spread"] = t005_delta
    result["t009_provides_clearer_separation_than_t005_baseline"] = (
        t005_delta is not None and abs(t009_delta) > abs(t005_delta)
    )
    return result


def _max_t005_bucket_spread(t005_summary: dict[str, Any]) -> float | None:
    spreads = []
    for report in t005_summary.get("feature_reports", {}).values():
        values = [
            _float_or_none(row.get("median_fdv_proxy_runup_120m"))
            for row in report.get("bucket_tables", [])
        ]
        values = [value for value in values if value is not None]
        if values:
            spreads.append(max(values) - min(values))
    return max(spreads) if spreads else None


def _field_coverage_audit(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {field: _coverage(rows, field) for field in AUDIT_FIELDS}


def _coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    available = sum(1 for row in rows if _feature_value(row, field) is not None)
    total = len(rows)
    return {
        "available_rows": available,
        "missing_rows": total - available,
        "coverage_pct": _pct(available, total),
    }


def _warning_flags(
    *,
    rows: list[dict[str, Any]],
    field_audit: dict[str, dict[str, Any]],
    feature_warnings: list[str],
    holder_state_snapshots_path: Path | str | None,
    entity_proxy_path: Path | str | None,
    migration_labels_path: Path | str | None,
) -> list[str]:
    warnings = set(feature_warnings)
    warnings.add("true_market_cap_claims_blocked")
    if holder_state_snapshots_path:
        warnings.add("holder_state_observed_delta_replay_not_full_chain_state")
    else:
        warnings.add("holder_state_sidecar_not_provided")
    if entity_proxy_path:
        if field_audit["repeated_actor_overlap_proxy"]["coverage_pct"] < 95:
            warnings.add("entity_proxy_partial_coverage")
    else:
        warnings.add("entity_proxy_sidecar_not_provided")
    if not migration_labels_path:
        warnings.add("migration_context_not_provided")
    min_group = min(_interaction_summary(rows)["counts"].values(), default=0)
    if min_group < 30:
        warnings.add("small_interaction_group_counts")
    return sorted(warnings)


def _classify(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    comparisons: dict[str, Any],
    robustness: dict[str, Any],
    warning_flags: list[str],
) -> str:
    if len(rows) < 100 or "small_interaction_group_counts" in warning_flags:
        return "data_limited"
    primary = comparisons["fast_and_broad_vs_fast_and_narrow"]
    if not primary.get("left_outperformed_descriptively"):
        return "no_signal"
    trimmed_1 = robustness["exclude_top_1pct_fdv_proxy_runups"]["fast_and_broad_vs_fast_and_narrow"]
    trimmed_5 = robustness["exclude_top_5pct_fdv_proxy_runups"]["fast_and_broad_vs_fast_and_narrow"]
    if trimmed_1.get("left_outperformed_descriptively") and trimmed_5.get("left_outperformed_descriptively"):
        return "descriptive_signal_present"
    return "weak_signal"


def _limitations(warning_flags: list[str]) -> list[str]:
    limitations = [
        "FDV proxy outcomes are used; true market-cap claims remain blocked.",
        "This is descriptive only and does not create a trading rule.",
        "Quantile buckets are predefined for description, not optimized thresholds.",
    ]
    if "holder_state_observed_delta_replay_not_full_chain_state" in warning_flags:
        limitations.append("Holder-state overlays are observed delta replay, not confirmed full-chain account snapshots.")
    if "entity_proxy_partial_coverage" in warning_flags:
        limitations.append("Entity/concentration overlays are partial because sidecar coverage is not all-collected.")
    if "small_interaction_group_counts" in warning_flags:
        limitations.append("At least one interaction cell is small, limiting interpretation.")
    return limitations


def _next_recommendation(classification: str) -> str:
    if classification in {"descriptive_signal_present", "weak_signal"}:
        return "Run a separate chronological robustness review for T009. Do not promote this thesis from this sprint."
    if classification == "no_signal":
        return "Proceed to T010 Funding Lineage using the completed funding-link pilot."
    return "Resolve data coverage limits before interpreting T009."


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "launch_rows"}


def _markdown_summary(report: dict[str, Any]) -> str:
    comp = report["main_comparisons"]["fast_and_broad_vs_fast_and_narrow"]
    lines = [
        "# T009 Fast + Broad Early Launch Quality",
        "",
        f"- Final classification: `{report['final_classification']}`",
        f"- Dataset used: `{report['dataset']['dataset_scope']}`",
        f"- Launches analyzed: `{report['dataset']['launch_count']}`",
        f"- Speed feature: `{report['selected_features']['speed_feature_used']}`",
        f"- Breadth feature: `{report['selected_features']['breadth_feature_used']}`",
        f"- Fast and broad outperformed fast and narrow: `{comp.get('left_outperformed_descriptively')}`",
        f"- Median runup delta: `{comp.get('median_runup_delta')}`",
        f"- T005 baseline classification: `{report['t005_baseline_comparison'].get('t005_classification')}`",
        f"- T009 clearer than T005 baseline: `{report['t005_baseline_comparison'].get('t009_provides_clearer_separation_than_t005_baseline')}`",
        "",
        "## Interaction Group Counts",
        "",
    ]
    for group, count in report["interaction_groups"]["counts"].items():
        lines.append(f"- `{group}`: `{count}`")
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            "- No thesis promotion was made.",
            "- No backtest or walk-forward validation was run.",
            "- No trading rules were generated.",
            "- No profitability claims were made.",
            "",
            "## Warning Flags",
            "",
        ]
    )
    lines.extend(f"- `{flag}`" for flag in report["warning_flags"])
    lines.extend(["", "## Next Recommendation", "", report["next_recommendation"], ""])
    return "\n".join(lines)


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    group_counts = report["interaction_groups"]["counts"]
    fields = report["selected_features"]
    return "\n".join(
        [
            "# T009 FAST + BROAD EARLY LAUNCH QUALITY STATUS",
            "",
            "## Thesis Description",
            "",
            report["hypothesis"],
            "",
            "## Dataset",
            "",
            f"- Dataset used: `{report['dataset']['dataset_scope']}`",
            f"- Launch count: `{report['dataset']['launch_count']}`",
            f"- Speed feature used: `{fields['speed_feature_used']}`",
            f"- Breadth feature used: `{fields['breadth_feature_used']}`",
            f"- Concentration fields used: `{fields['concentration_fields_used']}`",
            "",
            "## Interaction Group Counts",
            "",
            *[f"- `{group}`: `{count}`" for group, count in group_counts.items()],
            "",
            "## Classification",
            "",
            f"- Classification: `{report['final_classification']}`",
            f"- Chronological robustness recommended: `{report['chronological_robustness_recommended']}`",
            "",
            "## Comparison To T005 Baseline",
            "",
            f"- T005 classification: `{report['t005_baseline_comparison'].get('t005_classification')}`",
            f"- T009 clearer than T005 baseline: `{report['t005_baseline_comparison'].get('t009_provides_clearer_separation_than_t005_baseline')}`",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Guardrails",
            "",
            "- No thesis promotion was made.",
            "- No validation, backtest, walk-forward, paper/live trading, trading logic, optimization, grid search, or ML workflow was run.",
            "- No trading rules were generated.",
            "",
            "## Outputs",
            "",
            f"- Markdown summary: `{markdown_path}`",
            f"- JSON summary: `{json_path}`",
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
        ]
    )


def _reproducible_command(
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    holder_state_snapshots_path: Path | str | None,
    entity_proxy_path: Path | str | None,
    migration_labels_path: Path | str | None,
    t005_summary_path: Path | str | None,
    dataset_scope: str,
) -> str:
    parts = [
        "./trading_env/bin/python -m research.mtp_research.validation.run_fast_broad_launch_quality_thesis",
        f'--snapshots-path "{snapshots_path}"',
        f'--outcomes-path "{outcomes_path}"',
        f'--dataset-scope "{dataset_scope}"',
    ]
    if holder_state_snapshots_path:
        parts.append(f'--holder-state-snapshots-path "{holder_state_snapshots_path}"')
    if entity_proxy_path:
        parts.append(f'--entity-proxy-path "{entity_proxy_path}"')
    if migration_labels_path:
        parts.append(f'--migration-labels-path "{migration_labels_path}"')
    if t005_summary_path:
        parts.append(f'--t005-summary-path "{t005_summary_path}"')
    return " ".join(parts)


def _migration_context(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_mint = {}
    by_creator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        creator = row.get("creator")
        if creator:
            by_creator[creator].append(row)
    for creator_rows in by_creator.values():
        creator_rows.sort(key=lambda row: row.get("launch_ts") or 0)
        prior = 0
        for row in creator_rows:
            migrated = bool(
                row.get("pumpfun_migrate_event_observed")
                or row.get("graduated_to_pumpswap")
                or row.get("migrated_to_raydium")
                or row.get("dex_pair_detected")
            )
            by_mint[_mint(row)] = {
                "creator_prior_migration_or_graduation_count": prior,
                "migration_or_graduation_observed": migrated,
            }
            if migrated and row.get("migration_time"):
                prior += 1
    return by_mint


def _holder_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for row in rows:
        mint = _mint(row)
        if mint:
            grouped[mint].append(row)
    return dict(grouped)


def _nearest_holder(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    if not rows:
        return None
    return min(rows, key=lambda row: abs(int(row.get("snapshot_age_seconds", 0)) - age))


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


def _read_json(path: Path | str | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for row in rows:
        mint = _mint(row)
        if mint:
            grouped[mint].append(row)
    return dict(grouped)


def _mint(row: dict[str, Any]) -> str | None:
    return row.get("token_mint") or row.get("mint")


def _creator(*rows: dict[str, Any]) -> str | None:
    for row in rows:
        if row.get("creator"):
            return row.get("creator")
        metadata = row.get("metadata_json") or {}
        if metadata.get("creator_deployer"):
            return metadata.get("creator_deployer")
        if metadata.get("creator_wallet"):
            return metadata.get("creator_wallet")
    return None


def _feature_value(row: dict[str, Any], field: str) -> float | None:
    return _float_or_none((row.get("features") or {}).get(field))


def _outcome_value(row: dict[str, Any], field: str) -> float | None:
    return _float_or_none((row.get("outcomes") or {}).get(field))


def _nested_float(row: dict[str, Any], parent: str, child: str) -> float | None:
    value = row.get(parent)
    if isinstance(value, dict):
        return _float_or_none(value.get(child))
    return None


def _event_count(snapshot: dict[str, Any]) -> float | None:
    metadata = snapshot.get("metadata_json") or {}
    return _first_float(metadata.get("event_count"), snapshot.get("event_count"), snapshot.get("tx_count"))


def _holder_value(holder: dict[str, Any] | None, field: str) -> float | None:
    return _float_or_none(holder.get(field)) if holder else None


def _ratio(numerator: Any, denominator: Any) -> float | None:
    n = _float_or_none(numerator)
    d = _float_or_none(denominator)
    if n is None or d in (None, 0):
        return None
    return n / d


def _rate(rows: list[dict[str, Any]], field: str) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if row["outcomes"].get(field)) / len(rows)


def _delta(left: dict[str, Any], right: dict[str, Any], field: str) -> float | None:
    lval = _float_or_none(left.get(field))
    rval = _float_or_none(right.get(field))
    if lval is None or rval is None:
        return None
    return lval - rval


def _outperformed(left: dict[str, Any], right: dict[str, Any]) -> bool | None:
    runup_delta = _delta(left, right, "median_fdv_proxy_runup_120m")
    if runup_delta is None:
        return None
    drawdown_delta = _delta(left, right, "median_fdv_proxy_drawdown_120m")
    return runup_delta > 0 and (drawdown_delta is None or drawdown_delta >= 0)


def _median_or_none(values: list[float]) -> float | None:
    return median(values) if values else None


def _first_float(*values: Any) -> float | None:
    for value in values:
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
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
    return _safe_round((part / total) * 100) if total else 0.0


def _safe_round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
