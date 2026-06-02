"""Short-window explosive expansion discovery labels and audit."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


REPORT_ID = "short_window_expansion_discovery_v0"
TRIGGERS = {"trigger_15k": 15_000.0, "trigger_20k": 20_000.0, "trigger_30k": 30_000.0}
MAX_WINDOWS = {"1m": 60, "2m": 120, "5m": 300, "10m": 600, "30m": 1800}
MIN_WINDOWS = {"1m": 60, "5m": 300, "30m": 1800}
READINESS_READY = "short_window_expansion_ready_for_formal_thesis"
READINESS_PARTIAL = "short_window_expansion_partial_needs_more_forward_path"
READINESS_BLOCKED = "short_window_expansion_blocked"


def build_short_window_expansion_discovery_report(
    *,
    snapshots_path: Path | str,
    holder_state_snapshots_path: Path | str | None = None,
    entity_proxy_path: Path | str | None = None,
    migration_labels_path: Path | str | None = None,
    funding_link_path: Path | str | None = None,
) -> dict[str, Any]:
    snapshots = _read_jsonl(snapshots_path)
    by_mint = _group_by_mint(snapshots)
    holder_by_mint = _sidecar_by_mint(_read_jsonl(holder_state_snapshots_path)) if holder_state_snapshots_path else {}
    entity_by_mint = _sidecar_by_mint(_read_jsonl(entity_proxy_path)) if entity_proxy_path else {}
    migration_by_mint = _migration_by_mint(_read_jsonl(migration_labels_path)) if migration_labels_path else {}
    funding_by_mint = _sidecar_by_mint(_read_table(funding_link_path)) if funding_link_path else {}
    label_rows = []
    launch_missing_reasons = Counter()
    for mint, rows in sorted(by_mint.items()):
        ordered = _priced_snapshots(rows)
        if not ordered:
            launch_missing_reasons["no_priced_snapshots"] += 1
            continue
        for trigger_name, threshold in TRIGGERS.items():
            label = _label_for_trigger(
                mint=mint,
                snapshots=ordered,
                trigger_name=trigger_name,
                threshold=threshold,
                holder=holder_by_mint.get(mint, [{}])[0],
                entity=entity_by_mint.get(mint, [{}])[0],
                migration=migration_by_mint.get(mint, {}),
                funding=funding_by_mint.get(mint, [{}])[0],
            )
            if label:
                label_rows.append(label)
            else:
                launch_missing_reasons[f"{trigger_name}_not_reached"] += 1
    trigger_feasibility = _trigger_feasibility(label_rows, len(by_mint), launch_missing_reasons)
    pattern = _pattern_discovery(label_rows)
    readiness = _readiness(label_rows, trigger_feasibility, pattern)
    return {
        "report_id": REPORT_ID,
        "dataset": {
            "snapshots_path": str(snapshots_path),
            "holder_state_snapshots_path": str(holder_state_snapshots_path) if holder_state_snapshots_path else None,
            "entity_proxy_path": str(entity_proxy_path) if entity_proxy_path else None,
            "migration_labels_path": str(migration_labels_path) if migration_labels_path else None,
            "funding_link_path": str(funding_link_path) if funding_link_path else None,
            "launches_analyzed": len(by_mint),
            "snapshot_count": len(snapshots),
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "methodology_flags": [
            "research_only",
            "data_discovery_and_labeling_only",
            "no_thesis_promotion",
            "no_backtest",
            "no_walk_forward_validation",
            "no_paper_trading",
            "no_live_trading",
            "no_auto_buy_sell",
            "no_wallet_execution",
            "no_trading_rules",
            "no_profitability_claims",
            "no_entry_exit_logic",
            "no_execution_recommendations",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_future_leakage",
            "fdv_proxy_not_true_market_cap",
        ],
        "data_source_audit": _data_source_audit(snapshots, holder_by_mint, entity_by_mint, migration_by_mint, funding_by_mint),
        "dexscreener_public_api_support": _dexscreener_public_api_support(),
        "trigger_feasibility": trigger_feasibility,
        "label_summary": _label_summary(label_rows),
        "pattern_discovery": pattern,
        "current_market_observation_design": _current_market_observation_design(),
        "label_rows": label_rows,
        "readiness_classification": readiness,
        "warning_flags": _warning_flags(readiness, trigger_feasibility, pattern),
        "next_recommendation": _next_recommendation(readiness),
    }


def write_short_window_expansion_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    labels_json = output / "short_window_expansion_labels.json"
    labels_parquet = output / "short_window_expansion_labels.parquet"
    summary_json = output / "short_window_expansion_discovery_summary.json"
    summary_md = output / "short_window_expansion_discovery_summary.md"
    labels_json.write_text(json.dumps(report["label_rows"], indent=2, sort_keys=True), encoding="utf-8")
    _write_parquet(report["label_rows"], labels_parquet)
    summary_json.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    summary_md.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, summary_md, summary_json, labels_json, labels_parquet), encoding="utf-8")
    return {
        "labels_json_path": labels_json,
        "labels_parquet_path": labels_parquet,
        "summary_json_path": summary_json,
        "summary_markdown_path": summary_md,
        "status_path": status,
    }


def _label_for_trigger(
    *,
    mint: str,
    snapshots: list[dict[str, Any]],
    trigger_name: str,
    threshold: float,
    holder: dict[str, Any],
    entity: dict[str, Any],
    migration: dict[str, Any],
    funding: dict[str, Any],
) -> dict[str, Any] | None:
    trigger = next((row for row in snapshots if (_value(row) or 0) >= threshold), None)
    if not trigger:
        return None
    trigger_age = int(trigger.get("launch_age_seconds") or 0)
    trigger_ts = _int_or_none(trigger.get("snapshot_ts")) or (_int_or_none(trigger.get("launch_ts")) or 0) + trigger_age
    trigger_value = _value(trigger)
    forward = [row for row in snapshots if int(row.get("launch_age_seconds") or 0) >= trigger_age]
    row = {
        "launch_id": trigger.get("launch_id"),
        "token_mint": mint,
        "trigger_name": trigger_name,
        "trigger_threshold": threshold,
        "trigger_time": trigger_ts,
        "trigger_age_seconds": trigger_age,
        "trigger_fdv_proxy": trigger_value,
        "forward_path_covered_to_30m": any(_age(row) >= trigger_age + 1800 for row in forward),
        "features_at_trigger": _features_at_trigger(trigger, holder, entity, migration, funding),
    }
    for label, seconds in MAX_WINDOWS.items():
        row[f"max_fdv_proxy_{label}_after_trigger"] = _max_value(forward, trigger_age, seconds)
    for label, seconds in MIN_WINDOWS.items():
        row[f"min_fdv_proxy_{label}_after_trigger"] = _min_value(forward, trigger_age, seconds)
    row.update(
        {
            "hit_50k_within_1m": _hit_abs(forward, trigger_age, 60, 50_000),
            "hit_50k_within_2m": _hit_abs(forward, trigger_age, 120, 50_000),
            "hit_50k_within_5m": _hit_abs(forward, trigger_age, 300, 50_000),
            "hit_100k_within_5m": _hit_abs(forward, trigger_age, 300, 100_000),
            "hit_100k_within_10m": _hit_abs(forward, trigger_age, 600, 100_000),
            "hit_100k_within_30m": _hit_abs(forward, trigger_age, 1800, 100_000),
        }
    )
    target_2x = _target_before_stop(forward, trigger_age, trigger_value, target_multiple=2, stop_drawdown=0.30)
    target_3x = _target_before_stop(forward, trigger_age, trigger_value, target_multiple=3, stop_drawdown=0.30)
    target_5x = _target_before_stop(forward, trigger_age, trigger_value, target_multiple=5, stop_drawdown=0.40)
    row.update(
        {
            "hit_2x_before_down_30pct": target_2x["hit"],
            "hit_3x_before_down_30pct": target_3x["hit"],
            "hit_5x_before_down_40pct": target_5x["hit"],
            "failed_down_30pct_before_2x": target_2x["failed_before_target"],
            "time_to_2x_seconds": target_2x["time_to_target_seconds"],
            "time_to_50k_seconds": _time_to_abs(forward, trigger_age, 50_000),
            "time_to_failure_seconds": target_2x["time_to_failure_seconds"],
            "drops_20pct_before_target": _drawdown_before_abs_target(forward, trigger_age, trigger_value, 0.20, 50_000),
            "drops_30pct_before_target": target_2x["failed_before_target"],
            "drops_50pct_before_target": _drawdown_before_abs_target(forward, trigger_age, trigger_value, 0.50, 50_000),
            "no_meaningful_expansion_within_5m": not row["hit_50k_within_5m"] and not target_2x["hit"],
            "no_meaningful_expansion_within_10m": not row["hit_100k_within_10m"] and not target_2x["hit"],
            "no_meaningful_expansion_within_30m": not row["hit_100k_within_30m"] and not target_2x["hit"],
        }
    )
    return row


def _features_at_trigger(
    snapshot: dict[str, Any],
    holder: dict[str, Any],
    entity: dict[str, Any],
    migration: dict[str, Any],
    funding: dict[str, Any],
) -> dict[str, Any]:
    events = _event_count(snapshot)
    actors = _float_or_none(snapshot.get("unique_actors"))
    buys = _float_or_none(snapshot.get("buy_count"))
    return {
        "valuation_proxy_usd_1m": _value(snapshot),
        "growth_into_trigger": _float_or_none(snapshot.get("price_change_since_launch")),
        "time_to_trigger": _age(snapshot),
        "buy_count_60s": buys,
        "event_count_60s": events,
        "active_wallets_60s": _float_or_none(snapshot.get("active_wallets")),
        "unique_actors_60s": actors,
        "events_per_actor": _ratio(events, actors),
        "buys_per_actor": _ratio(buys, actors),
        "top_holder_share": _float_or_none(holder.get("top_holder_share")),
        "top_10_holder_share": _float_or_none(holder.get("top_10_holder_share")),
        "creator_holder_share": _float_or_none(holder.get("creator_holder_share")),
        "repeated_actor_overlap_proxy": _float_or_none(entity.get("repeated_actor_overlap_proxy")),
        "repeated_buyer_overlap_proxy": _float_or_none(entity.get("repeated_buyer_overlap_proxy")),
        "synchronized_participation_proxy": _float_or_none(entity.get("synchronized_participation_proxy")),
        "circularity_proxy": _float_or_none(entity.get("circularity_proxy")),
        "churn_proxy": _float_or_none(entity.get("churn_proxy")),
        "creator_prior_migration_or_graduation_count": _float_or_none(
            migration.get("creator_prior_migration_or_graduation_count")
        ),
        "funding_source_available": bool(funding.get("candidate_funding_wallet")),
        "repeated_funder_flag": bool((funding.get("launches_sharing_funder") or 0) > 1),
        "future_snapshot_used": False,
    }


def _trigger_feasibility(label_rows: list[dict[str, Any]], launch_count: int, missing: Counter) -> dict[str, Any]:
    output = {}
    for trigger in TRIGGERS:
        rows = [row for row in label_rows if row["trigger_name"] == trigger]
        forward = [row for row in rows if row["forward_path_covered_to_30m"]]
        output[trigger] = {
            "launches_with_trigger": len(rows),
            "trigger_timestamp_coverage_pct": _pct(len(rows), launch_count),
            "forward_path_30m_count": len(forward),
            "forward_path_30m_coverage_pct": _pct(len(forward), len(rows)),
            "missing_reason_count": missing.get(f"{trigger}_not_reached", 0),
        }
    return output


def _label_summary(label_rows: list[dict[str, Any]]) -> dict[str, Any]:
    output = {}
    for trigger in TRIGGERS:
        rows = [row for row in label_rows if row["trigger_name"] == trigger]
        output[trigger] = {
            "label_count": len(rows),
            "hit_50k_within_5m_count": sum(1 for row in rows if row["hit_50k_within_5m"]),
            "hit_100k_within_10m_count": sum(1 for row in rows if row["hit_100k_within_10m"]),
            "hit_2x_before_down_30pct_count": sum(1 for row in rows if row["hit_2x_before_down_30pct"]),
            "failed_down_30pct_before_2x_count": sum(1 for row in rows if row["failed_down_30pct_before_2x"]),
        }
    return output


def _pattern_discovery(label_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in label_rows if row["trigger_name"] == "trigger_20k"]
    _assign_speed_breadth(rows)
    fast_narrow = [row for row in rows if row.get("interaction_group") == "fast_narrow"]
    fast_broad = [row for row in rows if row.get("interaction_group") == "fast_broad"]
    primary = "hit_2x_before_down_30pct"
    return {
        "primary_label": primary,
        "trigger_used": "trigger_20k",
        "trigger_universe_count": len(rows),
        "fast_narrow_vs_fast_broad": {
            "fast_narrow_count": len(fast_narrow),
            "fast_broad_count": len(fast_broad),
            "fast_narrow_hit_rate": _bool_rate(fast_narrow, primary),
            "fast_broad_hit_rate": _bool_rate(fast_broad, primary),
            "fast_narrow_minus_fast_broad": _rate_delta(fast_narrow, fast_broad, primary),
        },
        "diagnostic_comparisons": {
            "funding_source_available": _compare_bool_feature(rows, "funding_source_available", primary),
            "repeated_funder_flag": _compare_bool_feature(rows, "repeated_funder_flag", primary),
            "prior_migration_context": _compare_positive_feature(
                rows, "creator_prior_migration_or_graduation_count", primary
            ),
        },
        "dominance": _dominance(rows),
    }


def _assign_speed_breadth(rows: list[dict[str, Any]]) -> None:
    _assign_quantile(rows, "valuation_proxy_usd_1m", "speed_bucket", ("low_speed", "medium_speed", "high_speed"))
    _assign_quantile(rows, "active_wallets_60s", "breadth_bucket", ("low_breadth", "medium_breadth", "high_breadth"))
    for row in rows:
        if row.get("speed_bucket") == "high_speed" and row.get("breadth_bucket") == "low_breadth":
            row["interaction_group"] = "fast_narrow"
        elif row.get("speed_bucket") == "high_speed" and row.get("breadth_bucket") == "high_breadth":
            row["interaction_group"] = "fast_broad"
        else:
            row["interaction_group"] = "other"


def _assign_quantile(rows: list[dict[str, Any]], field: str, target: str, labels: tuple[str, str, str]) -> None:
    usable = [(idx, _feature(row, field)) for idx, row in enumerate(rows)]
    usable = [(idx, value) for idx, value in usable if value is not None]
    usable.sort(key=lambda item: (item[1], rows[item[0]]["token_mint"]))
    n = len(usable)
    for rank, (idx, _value) in enumerate(usable):
        rows[idx][target] = labels[0] if rank < n / 3 else labels[1] if rank < (2 * n) / 3 else labels[2]


def _readiness(label_rows: list[dict[str, Any]], feasibility: dict[str, Any], pattern: dict[str, Any]) -> str:
    trigger_20 = feasibility["trigger_20k"]
    primary_count = sum(1 for row in label_rows if row["trigger_name"] == "trigger_20k" and row["hit_2x_before_down_30pct"])
    trigger_count = trigger_20["launches_with_trigger"]
    if trigger_count < 100:
        return READINESS_BLOCKED
    if trigger_20["forward_path_30m_coverage_pct"] < 60:
        return READINESS_PARTIAL
    hit_rate = primary_count / trigger_count if trigger_count else 0
    dominance_share = pattern["dominance"].get("top_launch_ts_share") or 0
    if 0.02 <= hit_rate <= 0.80 and dominance_share < 0.30:
        return READINESS_READY
    return READINESS_PARTIAL


def _data_source_audit(
    snapshots: list[dict[str, Any]],
    holder_by_mint: dict[str, list[dict[str, Any]]],
    entity_by_mint: dict[str, list[dict[str, Any]]],
    migration_by_mint: dict[str, dict[str, Any]],
    funding_by_mint: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    mints = {_mint(row) for row in snapshots if _mint(row)}
    fields = [
        "valuation_proxy_usd",
        "active_wallets",
        "buy_count",
        "sell_count",
        "tx_count",
        "liquidity_proxy",
    ]
    return {
        "all_collected_lifecycle_snapshots": {"rows": len(snapshots), "launches": len(mints)},
        "snapshot_field_coverage": {field: _snapshot_coverage(snapshots, field) for field in fields},
        "holder_state_launches": len(holder_by_mint),
        "entity_proxy_launches": len(entity_by_mint),
        "migration_label_launches": len(migration_by_mint),
        "funding_link_launches": len(funding_by_mint),
        "dexscreener_pair_detection_cached": len(migration_by_mint) > 0,
        "dexscreener_boost_or_paid_order_cached": False,
    }


def _dexscreener_public_api_support() -> dict[str, Any]:
    return {
        "source": "https://docs.dexscreener.com/api/reference",
        "network_fetch_performed": False,
        "pair_lookup_by_pair": True,
        "pair_lookup_by_token": True,
        "latest_boosted_tokens": True,
        "top_boosted_tokens": True,
        "latest_token_profiles": True,
        "latest_ads": True,
        "paid_order_checks": True,
        "current_pair_metadata": ["fdv", "marketCap", "liquidity", "txns", "volume", "priceChange", "pairCreatedAt"],
        "historical_forward_tracking": "not provided directly; requires observation or separate cached polling",
    }


def _current_market_observation_design() -> dict[str, Any]:
    return {
        "study_type": "bounded_live_observation_design_only",
        "continuous_monitoring_implemented": False,
        "target_tokens": "100_to_300",
        "chain": "solana",
        "first_seen_fdv_range": "10k_to_30k",
        "forward_tracking_window": "30m",
        "dry_run_command_shape": (
            "./trading_env/bin/python -m research.mtp_research.validation.run_dexscreener_observation_plan "
            "--chain solana --max-tokens 100 --fdv-min 10000 --fdv-max 30000 --forward-window-minutes 30 --dry-run"
        ),
        "implementation_status": "design_only_no_alerts_no_trading",
    }


def _warning_flags(readiness: str, feasibility: dict[str, Any], pattern: dict[str, Any]) -> list[str]:
    warnings = {"fdv_proxy_not_true_market_cap", "no_trading_claims"}
    if readiness != READINESS_READY:
        warnings.add("not_ready_for_formal_thesis")
    if feasibility["trigger_20k"]["forward_path_30m_coverage_pct"] < 60:
        warnings.add("limited_forward_path_coverage")
    if pattern["trigger_universe_count"] < 100:
        warnings.add("small_trigger_universe")
    return sorted(warnings)


def _next_recommendation(readiness: str) -> str:
    if readiness == READINESS_READY:
        return "Design a formal thesis next, likely focused on fast+narrow explosive expansion after trigger. Do not promote yet."
    if readiness == READINESS_PARTIAL:
        return "Improve forward-path coverage or add bounded DexScreener observation data before a formal thesis."
    return "Do not run a formal thesis yet; improve trigger/forward-path data or stop this line."


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "label_rows"}


def _markdown_summary(report: dict[str, Any]) -> str:
    label = report["label_summary"].get("trigger_20k", {})
    pattern = report["pattern_discovery"]["fast_narrow_vs_fast_broad"]
    lines = [
        "# Short-Window Expansion Discovery",
        "",
        f"- Readiness: `{report['readiness_classification']}`",
        f"- Launches analyzed: `{report['dataset']['launches_analyzed']}`",
        f"- Trigger 20k count: `{report['trigger_feasibility']['trigger_20k']['launches_with_trigger']}`",
        f"- Hit 50k within 5m: `{label.get('hit_50k_within_5m_count')}`",
        f"- Hit 100k within 10m: `{label.get('hit_100k_within_10m_count')}`",
        f"- Hit 2x before down 30pct: `{label.get('hit_2x_before_down_30pct_count')}`",
        f"- Fast narrow hit rate: `{pattern.get('fast_narrow_hit_rate')}`",
        f"- Fast broad hit rate: `{pattern.get('fast_broad_hit_rate')}`",
        "",
        "## Guardrails",
        "",
        "- No trading rules were generated.",
        "- No thesis promotion, validation, backtest, walk-forward, paper/live trading, or live trading was run.",
        "",
        "## Next Recommendation",
        "",
        report["next_recommendation"],
        "",
    ]
    return "\n".join(lines)


def _status_markdown(report: dict[str, Any], summary_md: Path, summary_json: Path, labels_json: Path, labels_parquet: Path) -> str:
    labels = report["label_summary"]["trigger_20k"]
    pattern = report["pattern_discovery"]["fast_narrow_vs_fast_broad"]
    return "\n".join(
        [
            "# Short-Window Expansion Discovery Status",
            "",
            "## Refocus Rationale",
            "",
            "The project is refocusing from launch survival/health toward short-window explosive expansion because prior descriptive health-oriented theses mostly failed or stayed weak, while T009 showed fast+narrow launches had stronger FDV-proxy runup than fast+broad launches.",
            "",
            "## Trigger Thresholds Tested",
            "",
            "- `15k`, `20k`, `30k` FDV-proxy triggers",
            "",
            "## Forward Windows Tested",
            "",
            "- `1m`, `2m`, `5m`, `10m`, `30m` max windows",
            "- `1m`, `5m`, `30m` min windows",
            "",
            "## Label Coverage",
            "",
            f"- Trigger 15k: `{report['trigger_feasibility']['trigger_15k']['launches_with_trigger']}`",
            f"- Trigger 20k: `{report['trigger_feasibility']['trigger_20k']['launches_with_trigger']}`",
            f"- Trigger 30k: `{report['trigger_feasibility']['trigger_30k']['launches_with_trigger']}`",
            "",
            "## Explosive Label Counts At Trigger 20k",
            "",
            f"- Hit 50k within 5m: `{labels['hit_50k_within_5m_count']}`",
            f"- Hit 100k within 10m: `{labels['hit_100k_within_10m_count']}`",
            f"- Hit 2x before down 30pct: `{labels['hit_2x_before_down_30pct_count']}`",
            "",
            "## Fast Narrow Vs Fast Broad",
            "",
            f"- Fast narrow hit rate: `{pattern['fast_narrow_hit_rate']}`",
            f"- Fast broad hit rate: `{pattern['fast_broad_hit_rate']}`",
            f"- Difference: `{pattern['fast_narrow_minus_fast_broad']}`",
            "",
            "## Readiness",
            "",
            f"- Classification: `{report['readiness_classification']}`",
            f"- Formal thesis justified next: `{report['readiness_classification'] == READINESS_READY}`",
            "",
            "## Limitations",
            "",
            "- FDV-proxy labels are not true market-cap labels.",
            "- Historical snapshots are launch-relative and coarse; live DexScreener/Axiom visibility may differ.",
            "- No trading or execution recommendation is made.",
            "",
            "## Outputs",
            "",
            f"- Labels JSON: `{labels_json}`",
            f"- Labels parquet: `{labels_parquet}`",
            f"- Summary JSON: `{summary_json}`",
            f"- Summary markdown: `{summary_md}`",
            "",
            "## Guardrails",
            "",
            "- No trading rules were generated.",
            "- No thesis promotion, validation, backtest, walk-forward, paper/live trading, live trading, optimization, grid search, or ML was run.",
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
        ]
    )


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


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
    output = {}
    for row in rows:
        mint = _mint(row)
        if mint:
            output[mint] = {
                "creator_prior_migration_or_graduation_count": row.get("creator_prior_migration_or_graduation_count"),
                "migration_or_graduation_observed": bool(row.get("dex_pair_detected") or row.get("graduated_to_pumpswap")),
            }
    return output


def _priced_snapshots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted([row for row in rows if _value(row) is not None], key=_age)


def _max_value(rows: list[dict[str, Any]], trigger_age: int, window: int) -> float | None:
    values = [_value(row) for row in rows if trigger_age <= _age(row) <= trigger_age + window]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _min_value(rows: list[dict[str, Any]], trigger_age: int, window: int) -> float | None:
    values = [_value(row) for row in rows if trigger_age <= _age(row) <= trigger_age + window]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _hit_abs(rows: list[dict[str, Any]], trigger_age: int, window: int, target: float) -> bool:
    return any((_value(row) or 0) >= target for row in rows if trigger_age <= _age(row) <= trigger_age + window)


def _time_to_abs(rows: list[dict[str, Any]], trigger_age: int, target: float) -> int | None:
    for row in rows:
        if _age(row) >= trigger_age and (_value(row) or 0) >= target:
            return _age(row) - trigger_age
    return None


def _target_before_stop(
    rows: list[dict[str, Any]],
    trigger_age: int,
    trigger_value: float | None,
    *,
    target_multiple: float,
    stop_drawdown: float,
) -> dict[str, Any]:
    if not trigger_value:
        return {"hit": False, "failed_before_target": False, "time_to_target_seconds": None, "time_to_failure_seconds": None}
    target = trigger_value * target_multiple
    stop = trigger_value * (1 - stop_drawdown)
    failure_time = None
    for row in rows:
        if _age(row) < trigger_age:
            continue
        value = _value(row)
        if value is None:
            continue
        dt = _age(row) - trigger_age
        if value <= stop:
            failure_time = dt
            return {"hit": False, "failed_before_target": True, "time_to_target_seconds": None, "time_to_failure_seconds": failure_time}
        if value >= target:
            return {"hit": True, "failed_before_target": False, "time_to_target_seconds": dt, "time_to_failure_seconds": failure_time}
    return {"hit": False, "failed_before_target": False, "time_to_target_seconds": None, "time_to_failure_seconds": failure_time}


def _drawdown_before_abs_target(
    rows: list[dict[str, Any]], trigger_age: int, trigger_value: float | None, drawdown: float, target: float
) -> bool:
    if not trigger_value:
        return False
    stop = trigger_value * (1 - drawdown)
    for row in rows:
        if _age(row) < trigger_age:
            continue
        value = _value(row)
        if value is None:
            continue
        if value <= stop:
            return True
        if value >= target:
            return False
    return False


def _compare_bool_feature(rows: list[dict[str, Any]], feature: str, label: str) -> dict[str, Any]:
    yes = [row for row in rows if row["features_at_trigger"].get(feature)]
    no = [row for row in rows if not row["features_at_trigger"].get(feature)]
    return {"yes_count": len(yes), "no_count": len(no), "yes_hit_rate": _bool_rate(yes, label), "no_hit_rate": _bool_rate(no, label)}


def _compare_positive_feature(rows: list[dict[str, Any]], feature: str, label: str) -> dict[str, Any]:
    yes = [row for row in rows if (_feature(row, feature) or 0) > 0]
    no = [row for row in rows if (_feature(row, feature) or 0) <= 0]
    return {"positive_count": len(yes), "zero_count": len(no), "positive_hit_rate": _bool_rate(yes, label), "zero_hit_rate": _bool_rate(no, label)}


def _dominance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"top_launch_ts_share": None}
    dates = Counter(int((row.get("trigger_time") or 0) // 86400) for row in rows if row.get("hit_2x_before_down_30pct"))
    if not dates:
        return {"top_launch_ts_share": 0.0}
    return {"top_launch_ts_share": dates.most_common(1)[0][1] / sum(dates.values())}


def _snapshot_coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    available = sum(1 for row in rows if row.get(field) is not None)
    return {"available_rows": available, "missing_rows": len(rows) - available, "coverage_pct": _pct(available, len(rows))}


def _bool_rate(rows: list[dict[str, Any]], field: str) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if row.get(field)) / len(rows)


def _rate_delta(left: list[dict[str, Any]], right: list[dict[str, Any]], field: str) -> float | None:
    lrate = _bool_rate(left, field)
    rrate = _bool_rate(right, field)
    if lrate is None or rrate is None:
        return None
    return lrate - rrate


def _feature(row: dict[str, Any], field: str) -> float | None:
    return _float_or_none((row.get("features_at_trigger") or {}).get(field))


def _value(row: dict[str, Any]) -> float | None:
    return _float_or_none(row.get("valuation_proxy_usd") if row.get("valuation_proxy_available") is not False else None)


def _event_count(row: dict[str, Any]) -> float | None:
    metadata = row.get("metadata_json") or {}
    return _float_or_none(metadata.get("event_count") or row.get("event_count") or row.get("tx_count"))


def _age(row: dict[str, Any]) -> int:
    return int(row.get("launch_age_seconds") or 0)


def _mint(row: dict[str, Any]) -> str | None:
    return row.get("token_mint") or row.get("mint")


def _ratio(numerator: Any, denominator: Any) -> float | None:
    n = _float_or_none(numerator)
    d = _float_or_none(denominator)
    if n is None or d in (None, 0):
        return None
    return n / d


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    parsed = _float_or_none(value)
    return int(parsed) if parsed is not None else None


def _pct(part: int, total: int) -> float:
    return round((part / total) * 100, 6) if total else 0.0
