"""Winner-anatomy discovery for explosive FDV-proxy runners."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any


REPORT_ID = "winner_anatomy_explosive_runners_v0"
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
PRIMARY_MILESTONES = ["50k", "100k", "200k", "500k", "1m"]
LAUNCH_RELATIVE_AGES = [30, 60, 120, 300, 600]
PRE_MILESTONE_OFFSETS = [30, 60, 120, 300]
HOLDER_BUCKETS = [
    ("0_to_49", 0, 49),
    ("50_to_99", 50, 99),
    ("100_to_199", 100, 199),
    ("200_to_499", 200, 499),
    ("500_to_999", 500, 999),
    ("1000_plus", 1000, None),
]
FDV_BUCKETS = [
    ("under_10k", None, 10_000),
    ("10k_to_20k", 10_000, 20_000),
    ("20k_to_50k", 20_000, 50_000),
    ("50k_to_100k", 50_000, 100_000),
    ("100k_to_200k", 100_000, 200_000),
    ("200k_to_500k", 200_000, 500_000),
    ("500k_to_1m", 500_000, 1_000_000),
    ("1m_plus", 1_000_000, None),
]
READY = "winner_anatomy_ready_for_formal_explosive_thesis"
PARTIAL = "winner_anatomy_partial_needs_better_forward_path"
BLOCKED = "winner_anatomy_blocked"


def build_winner_anatomy_explosive_runner_report(
    *,
    snapshots_path: Path | str,
    holder_state_snapshots_path: Path | str | None = None,
    entity_proxy_path: Path | str | None = None,
    migration_labels_path: Path | str | None = None,
    funding_link_path: Path | str | None = None,
) -> dict[str, Any]:
    snapshots = _read_jsonl(snapshots_path)
    holder_by_mint = _group_by_mint(_read_jsonl(holder_state_snapshots_path)) if holder_state_snapshots_path else {}
    entity_by_mint = _group_by_mint(_read_jsonl(entity_proxy_path)) if entity_proxy_path else {}
    migration_by_mint = _migration_by_mint(_read_jsonl(migration_labels_path)) if migration_labels_path else {}
    funding_by_mint = _group_by_mint(_read_table(funding_link_path)) if funding_link_path else {}
    grouped = _group_by_mint(snapshots)
    launch_rows = [
        _launch_row(mint, rows, holder_by_mint.get(mint, []), entity_by_mint.get(mint, []), migration_by_mint.get(mint, {}), funding_by_mint.get(mint, []))
        for mint, rows in sorted(grouped.items())
    ]
    pre_rows = _pre_milestone_snapshots(launch_rows)
    holder_fdv = _holder_fdv_relationship(launch_rows, snapshots, holder_by_mint)
    tier_anatomy = _tier_anatomy(launch_rows)
    explosive = _explosive_path_diagnostics(launch_rows)
    feature_ranking = _feature_family_ranking(launch_rows)
    readiness = _readiness(launch_rows, pre_rows, feature_ranking)
    return {
        "report_id": REPORT_ID,
        "dataset": {
            "snapshots_path": str(snapshots_path),
            "holder_state_snapshots_path": str(holder_state_snapshots_path) if holder_state_snapshots_path else None,
            "entity_proxy_path": str(entity_proxy_path) if entity_proxy_path else None,
            "migration_labels_path": str(migration_labels_path) if migration_labels_path else None,
            "funding_link_path": str(funding_link_path) if funding_link_path else None,
            "launches_analyzed": len(launch_rows),
            "snapshot_count": len(snapshots),
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "methodology_flags": [
            "research_only",
            "descriptive_discovery_only",
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
        "field_coverage_audit": _field_coverage(launch_rows, snapshots, holder_by_mint, entity_by_mint, migration_by_mint, funding_by_mint),
        "milestone_counts": _milestone_counts(launch_rows),
        "milestone_tier_counts": dict(Counter(row["milestone_tier"] for row in launch_rows)),
        "holder_fdv_relationship": holder_fdv,
        "pre_milestone_snapshots": pre_rows,
        "milestone_tier_anatomy": tier_anatomy,
        "explosive_path_diagnostics": explosive,
        "candidate_signal_discovery": feature_ranking,
        "launch_rows": launch_rows,
        "readiness_classification": readiness,
        "warning_flags": _warning_flags(readiness, launch_rows),
        "recommended_formal_thesis_next": _recommended_next_thesis(readiness, feature_ranking),
        "next_recommendation": _next_recommendation(readiness),
    }


def write_winner_anatomy_outputs(report: dict[str, Any], *, output_dir: Path | str, status_path: Path | str) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "T010_winner_anatomy_explosive_runners_summary.json"
    md_path = output / "T010_winner_anatomy_explosive_runners_summary.md"
    pre_csv = output / "winner_pre_milestone_snapshots.csv"
    holder_csv = output / "holder_fdv_relationship.csv"
    tier_csv = output / "milestone_tier_anatomy.csv"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_markdown_summary(report), encoding="utf-8")
    _write_csv(report["pre_milestone_snapshots"], pre_csv)
    _write_csv(_holder_fdv_csv_rows(report["holder_fdv_relationship"]), holder_csv)
    _write_csv(_tier_csv_rows(report["milestone_tier_anatomy"]), tier_csv)
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, json_path, md_path, pre_csv, holder_csv, tier_csv), encoding="utf-8")
    return {
        "json_summary_path": json_path,
        "markdown_summary_path": md_path,
        "pre_milestone_csv_path": pre_csv,
        "holder_fdv_csv_path": holder_csv,
        "milestone_tier_csv_path": tier_csv,
        "status_path": status,
    }


def _launch_row(
    mint: str,
    rows: list[dict[str, Any]],
    holders: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    migration: dict[str, Any],
    funding: list[dict[str, Any]],
) -> dict[str, Any]:
    priced = sorted([row for row in rows if _value(row) is not None], key=_age)
    crossings = {f"first_crossed_{name}": _first_crossing(priced, value) for name, value in MILESTONES.items()}
    peak = max(priced, key=lambda row: _value(row) or 0) if priced else {}
    return {
        "launch_id": _first_present(*(row.get("launch_id") for row in rows)),
        "token_mint": mint,
        "mint": mint,
        "creator": _creator(rows, migration, funding),
        "launch_ts": _int_or_none(_first_present(*(row.get("launch_ts") for row in rows))),
        "crossings": crossings,
        **{f"crossed_{name}_fdv_proxy": bool(crossings[f"first_crossed_{name}"]) for name in PRIMARY_MILESTONES},
        "peak_fdv_proxy": _value(peak),
        "time_to_peak_seconds": _age(peak) if peak else None,
        "milestone_tier": _tier(crossings),
        "feature_at_20k": _feature_snapshot(
            crossings.get("first_crossed_20k") or (_snapshot_view(peak) if peak else None),
            holders,
            entities,
            migration,
            funding,
        ),
        "priced_snapshots": priced,
        "holder_snapshots": holders,
    }


def _first_crossing(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    for row in rows:
        if (_value(row) or 0) >= threshold:
            return _snapshot_view(row)
    return None


def _snapshot_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "age_seconds": _age(row),
        "snapshot_ts": row.get("snapshot_ts"),
        "valuation_proxy_usd": _value(row),
        "holder_count": _float_or_none(row.get("holder_count")),
        "active_wallets": _float_or_none(row.get("active_wallets")),
        "unique_actors": _float_or_none(row.get("unique_actors")),
        "buy_count": _float_or_none(row.get("buy_count")),
        "sell_count": _float_or_none(row.get("sell_count")),
        "event_count": _event_count(row),
    }


def _tier(crossings: dict[str, dict[str, Any] | None]) -> str:
    if crossings["first_crossed_1m"]:
        return "reached_1m_plus"
    if crossings["first_crossed_500k"]:
        return "reached_500k_plus"
    if crossings["first_crossed_200k"]:
        return "reached_200k_but_never_500k"
    if crossings["first_crossed_100k"]:
        return "reached_100k_but_never_200k"
    if crossings["first_crossed_50k"]:
        return "reached_50k_but_never_100k"
    if crossings["first_crossed_20k"]:
        return "reached_20k_but_never_50k"
    return "never_reached_20k"


def _feature_snapshot(
    snapshot: dict[str, Any] | None,
    holders: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    migration: dict[str, Any],
    funding: list[dict[str, Any]],
) -> dict[str, Any]:
    if not snapshot:
        return {}
    age = snapshot["age_seconds"]
    holder = _nearest_holder(holders, age)
    entity = entities[0] if entities else {}
    funding_row = funding[0] if funding else {}
    return {
        "holder_count": _first_float(snapshot.get("holder_count"), holder.get("holder_count") if holder else None),
        "holder_growth_60s": _holder_growth(holders, age, 60),
        "holder_growth_120s": _holder_growth(holders, age, 120),
        "active_wallets": snapshot.get("active_wallets"),
        "unique_actors": snapshot.get("unique_actors"),
        "buy_count": snapshot.get("buy_count"),
        "sell_count": snapshot.get("sell_count"),
        "event_count": snapshot.get("event_count"),
        "buy_sell_ratio": _ratio(snapshot.get("buy_count"), snapshot.get("sell_count")),
        "events_per_actor": _ratio(snapshot.get("event_count"), snapshot.get("unique_actors")),
        "valuation_proxy_usd": snapshot.get("valuation_proxy_usd"),
        "fdv_per_event": _ratio(snapshot.get("valuation_proxy_usd"), snapshot.get("event_count")),
        "fdv_per_buy": _ratio(snapshot.get("valuation_proxy_usd"), snapshot.get("buy_count")),
        "top_holder_share": _float_or_none(holder.get("top_holder_share")) if holder else None,
        "top_10_holder_share": _float_or_none(holder.get("top_10_holder_share")) if holder else None,
        "creator_holder_share": _float_or_none(holder.get("creator_holder_share")) if holder else None,
        "creator_prior_migration_or_graduation_count": _float_or_none(migration.get("creator_prior_migration_or_graduation_count")),
        "repeated_actor_overlap_proxy": _float_or_none(entity.get("repeated_actor_overlap_proxy")),
        "synchronized_participation_proxy": _float_or_none(entity.get("synchronized_participation_proxy")),
        "circularity_proxy": _float_or_none(entity.get("circularity_proxy")),
        "churn_proxy": _float_or_none(entity.get("churn_proxy")),
        "funding_source_available": bool(funding_row.get("candidate_funding_wallet")),
        "repeated_funder_flag": bool((funding_row.get("launches_sharing_funder") or 0) > 1),
    }


def _pre_milestone_snapshots(launch_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in launch_rows:
        for trigger in ["15k", "20k", "30k", "50k"]:
            snap = row["crossings"].get(f"first_crossed_{trigger}")
            if snap:
                output.append(_pre_row(row, snap, trigger, f"trigger_first_{trigger}"))
        for milestone in ["100k", "200k", "500k", "1m"]:
            cross = row["crossings"].get(f"first_crossed_{milestone}")
            if not cross:
                continue
            for offset in PRE_MILESTONE_OFFSETS:
                snap = _snapshot_before(row["priced_snapshots"], cross["age_seconds"] - offset)
                if snap:
                    output.append(_pre_row(row, _snapshot_view(snap), milestone, f"{offset}s_before"))
        for age in LAUNCH_RELATIVE_AGES:
            snap = _snapshot_before(row["priced_snapshots"], age)
            if snap:
                output.append(_pre_row(row, _snapshot_view(snap), "launch_relative", f"{age}s"))
        if not row["crossed_100k_fdv_proxy"]:
            snap = row["crossings"].get("first_crossed_20k")
            context = "first_20k"
            if not snap and row["priced_snapshots"]:
                snap = _snapshot_view(max(row["priced_snapshots"], key=lambda item: _value(item) or 0))
                context = "peak_never_100k"
            if snap:
                output.append(_pre_row(row, snap, "non_winner", context))
    return output


def _pre_row(row: dict[str, Any], snap: dict[str, Any], milestone: str, context: str) -> dict[str, Any]:
    features = row["feature_at_20k"] if milestone == "non_winner" else _feature_snapshot(snap, row["holder_snapshots"], [], {}, [])
    return {
        "launch_id": row["launch_id"],
        "token_mint": row["token_mint"],
        "milestone": milestone,
        "snapshot_context": context,
        "snapshot_age_seconds": snap["age_seconds"],
        "valuation_proxy_usd": snap["valuation_proxy_usd"],
        "holder_count": features.get("holder_count"),
        "active_wallets": snap.get("active_wallets"),
        "buy_count": snap.get("buy_count"),
        "event_count": snap.get("event_count"),
        "milestone_tier": row["milestone_tier"],
    }


def _holder_fdv_relationship(
    launch_rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    holder_by_mint: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    paired = []
    for row in snapshots:
        holder = _float_or_none(row.get("holder_count"))
        if holder is None:
            holder = _nearest_holder_count(holder_by_mint.get(_mint(row), []), _age(row))
        fdv = _value(row)
        if holder is not None and fdv is not None:
            paired.append({"holder_count": holder, "fdv_proxy": fdv})
    return {
        "paired_snapshot_count": len(paired),
        "median_fdv_by_holder_bucket": _median_fdv_by_holder_bucket(paired),
        "median_holder_count_by_fdv_bucket": _median_holder_by_fdv_bucket(paired),
        "relationship_summary": _holder_fdv_summary(paired),
    }


def _median_fdv_by_holder_bucket(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {}
    for name, lo, hi in HOLDER_BUCKETS:
        vals = [row["fdv_proxy"] for row in rows if _in_bucket(row["holder_count"], lo, hi)]
        output[name] = _distribution(vals, value_name="median_fdv_proxy")
    return output


def _median_holder_by_fdv_bucket(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output = {}
    for name, lo, hi in FDV_BUCKETS:
        vals = [row["holder_count"] for row in rows if _in_bucket(row["fdv_proxy"], lo, hi)]
        output[name] = _distribution(vals, value_name="median_holder_count")
    return output


def _holder_fdv_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ratios = [
        {
            "fdv_proxy_per_holder": row["fdv_proxy"] / row["holder_count"],
            "holder_count_per_10k_fdv": row["holder_count"] / (row["fdv_proxy"] / 10_000),
        }
        for row in rows
        if row["holder_count"] not in (0, None) and row["fdv_proxy"]
    ]
    fdv_per_holder = [row["fdv_proxy_per_holder"] for row in ratios]
    holders_per_10k = [row["holder_count_per_10k_fdv"] for row in ratios]
    return {
        "fdv_proxy_per_holder": _distribution(fdv_per_holder, value_name="median"),
        "holder_count_per_10k_fdv": _distribution(holders_per_10k, value_name="median"),
        "interpretation": "stable_enough_to_formalize" if len(rows) >= 500 else "partial_or_noisy",
    }


def _tier_anatomy(launch_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped = defaultdict(list)
    for row in launch_rows:
        grouped[row["milestone_tier"]].append(row)
    fields = [
        "holder_count",
        "holder_growth_60s",
        "holder_growth_120s",
        "active_wallets",
        "buy_count",
        "sell_count",
        "event_count",
        "buy_sell_ratio",
        "events_per_actor",
        "fdv_per_event",
        "fdv_per_buy",
        "top_holder_share",
        "top_10_holder_share",
        "creator_holder_share",
        "creator_prior_migration_or_graduation_count",
        "repeated_actor_overlap_proxy",
        "funding_source_available",
        "repeated_funder_flag",
    ]
    return {
        tier: {
            "launch_count": len(rows),
            "feature_medians": {
                field: _median_feature(rows, field)
                for field in fields
            },
        }
        for tier, rows in sorted(grouped.items())
    }


def _explosive_path_diagnostics(launch_rows: list[dict[str, Any]]) -> dict[str, Any]:
    output = {}
    for tier in ["reached_100k_but_never_200k", "reached_200k_but_never_500k", "reached_500k_plus", "reached_1m_plus"]:
        rows = [row for row in launch_rows if row["milestone_tier"] == tier]
        output[tier] = {
            "launch_count": len(rows),
            "median_time_launch_to_20k": _median_cross_delta(rows, "20k"),
            "median_time_20k_to_50k": _median_between(rows, "20k", "50k"),
            "median_time_50k_to_100k": _median_between(rows, "50k", "100k"),
            "median_time_100k_to_200k": _median_between(rows, "100k", "200k"),
            "median_time_200k_to_500k": _median_between(rows, "200k", "500k"),
            "median_time_20k_to_peak": _median_time_20k_to_peak(rows),
            "holder_fdv_timing": _holder_fdv_timing(rows),
        }
    return output


def _feature_family_ranking(launch_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    winners = [row for row in launch_rows if row["crossed_100k_fdv_proxy"]]
    non = [row for row in launch_rows if row["crossings"].get("first_crossed_20k") and not row["crossed_100k_fdv_proxy"]]
    families = {
        "holder_count level": "holder_count",
        "holder acceleration": "holder_growth_60s",
        "active-wallet breadth": "active_wallets",
        "raw flow": "event_count",
        "top-holder concentration": "top_holder_share",
        "creator prior migration": "creator_prior_migration_or_graduation_count",
        "funding lineage": "funding_source_available",
        "entity proxy": "repeated_actor_overlap_proxy",
        "speed to $20k": None,
        "fast+narrow": None,
    }
    ranked = []
    for family, field in families.items():
        if field:
            wval = _median_feature(winners, field)
            nval = _median_feature(non, field)
            score = abs((wval or 0) - (nval or 0)) if wval is not None and nval is not None else 0
        elif family == "speed to $20k":
            wval = _median_cross_delta(winners, "20k")
            nval = _median_cross_delta(non, "20k")
            score = abs((wval or 0) - (nval or 0)) if wval is not None and nval is not None else 0
        else:
            wval = None
            nval = None
            score = 0
        ranked.append({"feature_family": family, "winner_median": wval, "non_winner_median": nval, "descriptive_score": score})
    return sorted(ranked, key=lambda row: row["descriptive_score"], reverse=True)


def _field_coverage(
    launch_rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    holder_by_mint: dict[str, list[dict[str, Any]]],
    entity_by_mint: dict[str, list[dict[str, Any]]],
    migration_by_mint: dict[str, dict[str, Any]],
    funding_by_mint: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "identity": {
            "launch_id": _row_coverage(launch_rows, "launch_id"),
            "mint": _row_coverage(launch_rows, "token_mint"),
            "creator": _row_coverage(launch_rows, "creator"),
            "launch_time": _row_coverage(launch_rows, "launch_ts"),
        },
        "valuation_path": {
            "valuation_proxy_usd_snapshots": _snapshot_coverage(snapshots, "valuation_proxy_usd"),
            "peak_fdv_proxy": _row_coverage(launch_rows, "peak_fdv_proxy"),
        },
        "holder_path": {
            "holder_state_launches": len(holder_by_mint),
            "holder_count_at_20k": _feature_coverage(launch_rows, "holder_count"),
        },
        "flow_participation": {
            "active_wallets": _snapshot_coverage(snapshots, "active_wallets"),
            "buy_count": _snapshot_coverage(snapshots, "buy_count"),
            "sell_count": _snapshot_coverage(snapshots, "sell_count"),
            "event_count": _snapshot_event_coverage(snapshots),
        },
        "entity_funding_reputation": {
            "entity_proxy_launches": len(entity_by_mint),
            "migration_label_launches": len(migration_by_mint),
            "funding_link_launches": len(funding_by_mint),
        },
    }


def _milestone_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {f"crossed_{name}_fdv_proxy": sum(1 for row in rows if row.get(f"crossed_{name}_fdv_proxy")) for name in PRIMARY_MILESTONES}
    counts["trigger_20k_count"] = sum(1 for row in rows if row["crossings"].get("first_crossed_20k"))
    return counts


def _readiness(rows: list[dict[str, Any]], pre_rows: list[dict[str, Any]], ranking: list[dict[str, Any]]) -> str:
    counts = _milestone_counts(rows)
    high_tier = counts["crossed_200k_fdv_proxy"] + counts["crossed_500k_fdv_proxy"]
    if counts["crossed_100k_fdv_proxy"] < 50 or counts["trigger_20k_count"] < 100:
        return BLOCKED
    if high_tier < 10 or len(pre_rows) < 200:
        return PARTIAL
    return READY


def _warning_flags(readiness: str, rows: list[dict[str, Any]]) -> list[str]:
    warnings = {"fdv_proxy_not_true_market_cap", "no_trading_claims"}
    if readiness != READY:
        warnings.add("not_ready_for_formal_thesis")
    if _milestone_counts(rows)["crossed_500k_fdv_proxy"] == 0:
        warnings.add("no_500k_examples")
    return sorted(warnings)


def _recommended_next_thesis(readiness: str, ranking: list[dict[str, Any]]) -> str | None:
    if readiness != READY or not ranking:
        return None
    return f"Formal explosive-runner thesis focused on {ranking[0]['feature_family']} before $100k/$200k crossings."


def _next_recommendation(readiness: str) -> str:
    if readiness == READY:
        return "Design a formal explosive-runner thesis from the highest-ranked pre-milestone feature family. Do not promote yet."
    if readiness == PARTIAL:
        return "Improve pre-crossing holder/entity coverage or add current-market observation before formal thesis testing."
    return "Do not run a formal thesis yet; improve milestone sample or forward-path data first."


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in report.items() if k == "launch_rows" or k != "launch_rows"}


def _markdown_summary(report: dict[str, Any]) -> str:
    counts = report["milestone_counts"]
    relationship = report["holder_fdv_relationship"]["relationship_summary"]["interpretation"]
    return "\n".join(
        [
            "# T010 Winner Anatomy / Explosive Runners",
            "",
            f"- Readiness: `{report['readiness_classification']}`",
            f"- Launches analyzed: `{report['dataset']['launches_analyzed']}`",
            f"- $20k trigger count: `{counts['trigger_20k_count']}`",
            f"- $50k winner count: `{counts['crossed_50k_fdv_proxy']}`",
            f"- $100k winner count: `{counts['crossed_100k_fdv_proxy']}`",
            f"- $200k winner count: `{counts['crossed_200k_fdv_proxy']}`",
            f"- $500k winner count: `{counts['crossed_500k_fdv_proxy']}`",
            f"- $1M winner count: `{counts['crossed_1m_fdv_proxy']}`",
            f"- Holder/FDV relationship: `{relationship}`",
            f"- Recommended next thesis: `{report['recommended_formal_thesis_next']}`",
            "",
            "No trading rules were generated.",
            "",
        ]
    )


def _status_markdown(report: dict[str, Any], json_path: Path, md_path: Path, pre_csv: Path, holder_csv: Path, tier_csv: Path) -> str:
    counts = report["milestone_counts"]
    ranking = report["candidate_signal_discovery"][:5]
    return "\n".join(
        [
            "# T010 Winner Anatomy Explosive Runners Status",
            "",
            "## Refocus Rationale",
            "",
            "The project is refocusing on short-window explosive expansion because prior health/survival-oriented thesis families mostly failed or were unstable. This sprint asks what explosive runners looked like before they became explosive runners.",
            "",
            "## Counts",
            "",
            f"- Launches analyzed: `{report['dataset']['launches_analyzed']}`",
            f"- $20k trigger count: `{counts['trigger_20k_count']}`",
            f"- $50k winner count: `{counts['crossed_50k_fdv_proxy']}`",
            f"- $100k winner count: `{counts['crossed_100k_fdv_proxy']}`",
            f"- $200k winner count: `{counts['crossed_200k_fdv_proxy']}`",
            f"- $500k winner count: `{counts['crossed_500k_fdv_proxy']}`",
            f"- $1M winner count: `{counts['crossed_1m_fdv_proxy']}`",
            "",
            "## Holder/FDV Relationship",
            "",
            f"- Summary: `{report['holder_fdv_relationship']['relationship_summary']['interpretation']}`",
            "",
            "## Strongest Pre-Milestone Differences",
            "",
            *[f"- `{row['feature_family']}` score `{row['descriptive_score']}`" for row in ranking],
            "",
            "## Interpretive Checks",
            "",
            f"- Holder count appears useful: `{_family_ranked(ranking, 'holder_count level')}`",
            f"- Fast+narrow appears useful: `{_family_ranked(ranking, 'fast+narrow')}`",
            f"- Dev migration appears useful: `{_family_ranked(ranking, 'creator prior migration')}`",
            f"- Funding lineage appears useful: `{_family_ranked(ranking, 'funding lineage')}`",
            f"- Higher-tier runners look different from $100k-only winners: `{_higher_tier_difference(report)}`",
            "",
            "## Readiness",
            "",
            f"- Classification: `{report['readiness_classification']}`",
            f"- Recommended formal thesis next: `{report['recommended_formal_thesis_next']}`",
            "",
            "## Limitations",
            "",
            "- FDV/valuation proxy is used; true market-cap claims remain blocked.",
            "- Holder-state sidecar coverage may be partial in the all-collected dataset.",
            "- This sprint is descriptive discovery only.",
            "",
            "## Outputs",
            "",
            f"- Summary JSON: `{json_path}`",
            f"- Summary markdown: `{md_path}`",
            f"- Pre-milestone CSV: `{pre_csv}`",
            f"- Holder/FDV CSV: `{holder_csv}`",
            f"- Tier anatomy CSV: `{tier_csv}`",
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


def _family_ranked(ranking: list[dict[str, Any]], family: str) -> bool:
    return any(row["feature_family"] == family and row["descriptive_score"] > 0 for row in ranking[:5])


def _higher_tier_difference(report: dict[str, Any]) -> bool:
    anatomy = report["milestone_tier_anatomy"]
    a = anatomy.get("reached_100k_but_never_200k", {}).get("feature_medians", {})
    b = anatomy.get("reached_500k_plus", {}).get("feature_medians", {})
    return bool(a and b and a != b)


def _holder_fdv_csv_rows(relationship: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for bucket, values in relationship["median_fdv_by_holder_bucket"].items():
        rows.append({"table": "median_fdv_by_holder_bucket", "bucket": bucket, **values})
    for bucket, values in relationship["median_holder_count_by_fdv_bucket"].items():
        rows.append({"table": "median_holder_count_by_fdv_bucket", "bucket": bucket, **values})
    return rows


def _tier_csv_rows(anatomy: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for tier, values in anatomy.items():
        row = {"tier": tier, "launch_count": values["launch_count"]}
        row.update(values["feature_medians"])
        rows.append(row)
    return rows


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    import csv

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


def _migration_by_mint(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        _mint(row): {
            "creator": row.get("creator"),
            "creator_prior_migration_or_graduation_count": row.get("creator_prior_migration_or_graduation_count"),
        }
        for row in rows if _mint(row)
    }


def _nearest_holder(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    return min(rows, key=lambda row: abs(_age_holder(row) - age)) if rows else None


def _nearest_holder_count(rows: list[dict[str, Any]], age: int) -> float | None:
    holder = _nearest_holder(rows, age)
    return _float_or_none(holder.get("holder_count")) if holder else None


def _holder_growth(rows: list[dict[str, Any]], age: int, window: int) -> float | None:
    now = _nearest_holder_count(rows, age)
    before = _nearest_holder_count(rows, max(0, age - window))
    if now is None or before is None:
        return None
    return now - before


def _snapshot_before(rows: list[dict[str, Any]], age: int) -> dict[str, Any] | None:
    eligible = [row for row in rows if _age(row) <= age]
    return max(eligible, key=_age) if eligible else None


def _in_bucket(value: float, lo: float | None, hi: float | None) -> bool:
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


def _distribution(values: list[float], *, value_name: str) -> dict[str, Any]:
    vals = [value for value in values if value is not None]
    if not vals:
        return {"sample_count": 0, value_name: None, "iqr": None, "min": None, "max": None}
    vals = sorted(vals)
    return {
        "sample_count": len(vals),
        value_name: median(vals),
        "iqr": [vals[len(vals) // 4], vals[(len(vals) * 3) // 4]],
        "min": vals[0],
        "max": vals[-1],
    }


def _median_feature(rows: list[dict[str, Any]], field: str) -> float | None:
    vals = [_float_or_none(row.get("feature_at_20k", {}).get(field)) for row in rows]
    vals = [value for value in vals if value is not None]
    return median(vals) if vals else None


def _median_cross_delta(rows: list[dict[str, Any]], milestone: str) -> float | None:
    vals = [row["crossings"].get(f"first_crossed_{milestone}", {}).get("age_seconds") for row in rows if row["crossings"].get(f"first_crossed_{milestone}")]
    return median(vals) if vals else None


def _median_between(rows: list[dict[str, Any]], start: str, end: str) -> float | None:
    vals = []
    for row in rows:
        a = row["crossings"].get(f"first_crossed_{start}")
        b = row["crossings"].get(f"first_crossed_{end}")
        if a and b:
            vals.append(b["age_seconds"] - a["age_seconds"])
    return median(vals) if vals else None


def _median_time_20k_to_peak(rows: list[dict[str, Any]]) -> float | None:
    vals = []
    for row in rows:
        cross = row["crossings"].get("first_crossed_20k")
        if cross and row.get("time_to_peak_seconds") is not None:
            vals.append(row["time_to_peak_seconds"] - cross["age_seconds"])
    return median(vals) if vals else None


def _holder_fdv_timing(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "data_limited"
    growth = [_float_or_none(row.get("feature_at_20k", {}).get("holder_growth_60s")) for row in rows]
    growth = [value for value in growth if value is not None]
    if not growth:
        return "holder_data_limited"
    med = median(growth)
    if med > 0:
        return "holders_and_fdv_move_together_or_holders_lead"
    return "fdv_leads_or_holder_growth_unobserved"


def _row_coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    available = sum(1 for row in rows if row.get(field) is not None)
    return {"available_rows": available, "missing_rows": len(rows) - available, "coverage_pct": _pct(available, len(rows))}


def _feature_coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    available = sum(1 for row in rows if row.get("feature_at_20k", {}).get(field) is not None)
    return {"available_rows": available, "missing_rows": len(rows) - available, "coverage_pct": _pct(available, len(rows))}


def _snapshot_coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    available = sum(1 for row in rows if row.get(field) is not None)
    return {"available_rows": available, "missing_rows": len(rows) - available, "coverage_pct": _pct(available, len(rows))}


def _snapshot_event_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    available = sum(1 for row in rows if _event_count(row) is not None)
    return {"available_rows": available, "missing_rows": len(rows) - available, "coverage_pct": _pct(available, len(rows))}


def _creator(rows: list[dict[str, Any]], migration: dict[str, Any], funding: list[dict[str, Any]]) -> str | None:
    if migration.get("creator"):
        return migration.get("creator")
    if funding and funding[0].get("creator"):
        return funding[0].get("creator")
    for row in rows:
        meta = row.get("metadata_json") or {}
        if meta.get("creator_deployer"):
            return meta["creator_deployer"]
    return None


def _mint(row: dict[str, Any]) -> str | None:
    return row.get("token_mint") or row.get("mint")


def _value(row: dict[str, Any]) -> float | None:
    return _float_or_none(row.get("valuation_proxy_usd") if row.get("valuation_proxy_available") is not False else None)


def _event_count(row: dict[str, Any]) -> float | None:
    meta = row.get("metadata_json") or {}
    return _first_float(meta.get("event_count"), row.get("event_count"), row.get("tx_count"))


def _age(row: dict[str, Any]) -> int:
    return int(row.get("launch_age_seconds") or 0)


def _age_holder(row: dict[str, Any]) -> int:
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
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    parsed = _float_or_none(value)
    return int(parsed) if parsed is not None else None


def _pct(part: int, total: int) -> float:
    return round((part / total) * 100, 6) if total else 0.0
