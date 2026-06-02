"""Historical date-expansion audit for explosive-runner research."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


REPORT_ID = "historical_date_expansion_v0"
TRIGGERS = {"15k": 15_000.0, "20k": 20_000.0, "30k": 30_000.0}
MILESTONES = {"50k": 50_000.0, "100k": 100_000.0, "200k": 200_000.0, "500k": 500_000.0, "1m": 1_000_000.0}
PREFERRED_TARGET = {
    "unique_20k_dates": 30,
    "total_20k_rows": 1_000,
    "median_rows_per_date": 10,
    "max_top_date_share": 0.35,
    "max_top3_date_share": 0.60,
    "min_forward_path_coverage": 0.90,
}


def build_historical_date_expansion(
    *,
    snapshots_path: Path | str,
    candidates_path: Path | str | None = None,
    output_root: Path | str,
    report_dir: Path | str,
    data_lake_root: Path | str | None = None,
) -> dict[str, Any]:
    snapshots = _read_jsonl(snapshots_path)
    candidates = _read_jsonl(candidates_path) if candidates_path else []
    by_mint = _group_by_mint(snapshots)
    launch_rows = [_launch_row(mint, rows) for mint, rows in sorted(by_mint.items())]
    launch_rows = [row for row in launch_rows if row is not None]
    labels = [_trigger_label(row) for row in launch_rows]
    coverage = _coverage_audit(launch_rows, labels, snapshots_path=snapshots_path, candidates=candidates)
    expanded_paths = _write_expanded_outputs(labels, launch_rows, snapshots, output_root)
    date_balance = _date_balance([row for row in labels if row.get("trigger_20k_time")])
    source_paths = _classify_sources(
        coverage=coverage,
        labels=labels,
        data_lake_root=Path(data_lake_root) if data_lake_root else None,
    )
    readiness = classify_readiness(
        unique_dates=date_balance["unique_dates"],
        total_20k_rows=date_balance["total_rows"],
        median_rows_per_date=date_balance["median_rows_per_active_date"] or 0,
        top_date_share=date_balance["top_date_share"] or 0,
        top3_date_share=date_balance["top3_date_share"] or 0,
        forward_path_coverage=coverage["forward_path_coverage"]["20k"],
        tiers_available=all(count > 0 for count in coverage["milestone_tier_counts"].values()),
        trigger_features_available=coverage["trigger_feature_coverage"]["event_count_at_20k"]["coverage_pct"] >= 90,
    )
    acquisition_plan = _acquisition_plan(source_paths, coverage, date_balance)
    summary = {
        "report_id": REPORT_ID,
        "guardrails": [
            "data_expansion_and_coverage_only",
            "no_thesis_rerun",
            "no_validation_run",
            "no_walk_forward_validation",
            "no_live_trading",
            "no_paper_trading",
            "no_auto_buy_sell",
            "no_wallet_execution",
            "no_order_routing",
            "no_profitability_claims",
            "no_strategy_generation",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "fdv_proxy_only",
        ],
        "previous_20k_trigger_dates": 3,
        "previous_20k_trigger_rows": 422,
        "expanded_20k_trigger_dates": date_balance["unique_dates"],
        "expanded_20k_trigger_rows": date_balance["total_rows"],
        "date_balance": date_balance,
        "coverage_audit": coverage,
        "expansion_paths": source_paths,
        "expanded_paths": {key: str(value) for key, value in expanded_paths.items()},
        "preferred_target": PREFERRED_TARGET,
        "preferred_target_met": readiness == "historical_expansion_ready_for_rerun",
        "date_balance_target_met": _date_balance_met(date_balance),
        "readiness_classification": readiness,
        "winner_anatomy_rerun_recommended": readiness == "historical_expansion_ready_for_rerun",
        "t011_rerun_recommended": readiness == "historical_expansion_ready_for_rerun",
        "external_acquisition_required": readiness != "historical_expansion_ready_for_rerun",
        "acquisition_plan": acquisition_plan,
        "expanded_trigger_labels": labels,
    }
    report_paths = _write_reports(summary, report_dir)
    summary["report_paths"] = {key: str(value) for key, value in report_paths.items()}
    return summary


def classify_readiness(
    *,
    unique_dates: int,
    total_20k_rows: int,
    median_rows_per_date: float,
    top_date_share: float,
    top3_date_share: float,
    forward_path_coverage: float,
    tiers_available: bool,
    trigger_features_available: bool,
) -> str:
    if (
        unique_dates >= PREFERRED_TARGET["unique_20k_dates"]
        and total_20k_rows >= PREFERRED_TARGET["total_20k_rows"]
        and median_rows_per_date >= PREFERRED_TARGET["median_rows_per_date"]
        and top_date_share <= PREFERRED_TARGET["max_top_date_share"]
        and top3_date_share < PREFERRED_TARGET["max_top3_date_share"]
        and forward_path_coverage >= PREFERRED_TARGET["min_forward_path_coverage"]
        and tiers_available
        and trigger_features_available
    ):
        return "historical_expansion_ready_for_rerun"
    if unique_dates == 0 or total_20k_rows == 0:
        return "historical_expansion_blocked"
    return "historical_expansion_requires_external_acquisition"


def write_status_and_plan(
    report: dict[str, Any],
    *,
    status_path: Path | str,
    plan_path: Path | str,
) -> dict[str, Path]:
    status = Path(status_path)
    plan = Path(plan_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    plan.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report), encoding="utf-8")
    plan.write_text(_plan_markdown(report), encoding="utf-8")
    return {"status_path": status, "plan_path": plan}


def _launch_row(mint: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    priced = sorted([row for row in rows if _value(row) is not None], key=_age)
    if not priced:
        return None
    launch_ts = _int_or_none(_first_present(*(row.get("launch_ts") for row in rows)))
    peak = max((_value(row) or 0) for row in priced)
    return {
        "launch_id": _first_present(*(row.get("launch_id") for row in rows)),
        "mint": mint,
        "token_mint": mint,
        "creator": _creator(rows),
        "launch_time": launch_ts,
        "launch_date": _date_key(launch_ts),
        "priced_snapshots": priced,
        "peak_fdv_proxy": peak,
    }


def _trigger_label(row: dict[str, Any]) -> dict[str, Any]:
    priced = row["priced_snapshots"]
    trigger_20 = _first_crossing(priced, TRIGGERS["20k"])
    label = {
        "launch_id": row.get("launch_id"),
        "mint": row.get("mint"),
        "creator": row.get("creator"),
        "launch_time": row.get("launch_time"),
        "launch_date": row.get("launch_date"),
        "trigger_15k_time": _crossing_time(priced, TRIGGERS["15k"]),
        "trigger_20k_time": _crossing_time(priced, TRIGGERS["20k"]),
        "trigger_30k_time": _crossing_time(priced, TRIGGERS["30k"]),
        "crossed_50k": bool(_first_crossing(priced, MILESTONES["50k"])),
        "crossed_100k": bool(_first_crossing(priced, MILESTONES["100k"])),
        "crossed_200k": bool(_first_crossing(priced, MILESTONES["200k"])),
        "crossed_500k": bool(_first_crossing(priced, MILESTONES["500k"])),
        "crossed_1m": bool(_first_crossing(priced, MILESTONES["1m"])),
        "forward_path_coverage": _forward_path_coverage(priced, trigger_20),
        "missing_reason": None,
    }
    for name, value in MILESTONES.items():
        label[f"time_to_{name}_from_20k"] = _time_delta_from_trigger(priced, trigger_20, value)
    if trigger_20:
        features = _trigger_features(trigger_20)
        label.update(features)
    else:
        label["missing_reason"] = "missing_20k_trigger"
    return label


def _trigger_features(row: dict[str, Any]) -> dict[str, Any]:
    events = _event_count(row)
    buys = _float_or_none(row.get("buy_count"))
    sells = _float_or_none(row.get("sell_count"))
    active = _float_or_none(row.get("active_wallets"))
    value = _value(row)
    return {
        "event_count_at_20k": events,
        "buy_count_at_20k": buys,
        "sell_count_at_20k": sells,
        "active_wallets_at_20k": active,
        "fdv_per_event_at_20k": _ratio(value, events),
        "fdv_per_buy_at_20k": _ratio(value, buys),
        "events_per_active_wallet_at_20k": _ratio(events, active),
        "buy_sell_ratio_at_20k": _ratio(buys, sells),
    }


def _coverage_audit(
    launch_rows: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    *,
    snapshots_path: Path | str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    launch_dates = Counter(row.get("launch_date") for row in launch_rows if row.get("launch_date"))
    trigger_counts = {
        name: _trigger_count_by_date(labels, f"trigger_{name}_time")
        for name in TRIGGERS
    }
    milestone_counts = {
        name: _milestone_count_by_date(labels, f"crossed_{name}")
        for name in MILESTONES
    }
    return {
        "snapshots_path": str(snapshots_path),
        "total_launches": len(launch_rows),
        "date_range": _date_range(launch_dates),
        "unique_launch_dates": len(launch_dates),
        "launches_per_date": dict(sorted(launch_dates.items())),
        "candidate_rows_available": len(candidates),
        "trigger_counts": trigger_counts,
        "milestone_counts": milestone_counts,
        "milestone_tier_counts": _tier_counts(labels),
        "forward_path_coverage": {
            "20k": _forward_coverage_rate(labels),
        },
        "missing_reason_counts": dict(Counter(row.get("missing_reason") or "none" for row in labels)),
        "trigger_feature_coverage": {
            field: _coverage(labels, field)
            for field in [
                "event_count_at_20k",
                "buy_count_at_20k",
                "sell_count_at_20k",
                "active_wallets_at_20k",
                "fdv_per_event_at_20k",
                "fdv_per_buy_at_20k",
                "events_per_active_wallet_at_20k",
            ]
        },
    }


def _date_balance(labels_20k: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["launch_date"] for row in labels_20k if row.get("launch_date"))
    values = list(counts.values())
    total = sum(values)
    top = counts.most_common()
    return {
        "unique_dates": len(counts),
        "total_rows": total,
        "median_rows_per_active_date": median(values) if values else 0,
        "min_rows_per_active_date": min(values) if values else 0,
        "max_rows_per_active_date": max(values) if values else 0,
        "top_date": top[0][0] if top else None,
        "top_date_share": _ratio(top[0][1], total) if top else 0,
        "top_3_dates": [date for date, _ in top[:3]],
        "top3_date_share": _ratio(sum(count for _, count in top[:3]), total) if top else 0,
        "date_distribution": dict(sorted(counts.items())),
    }


def _classify_sources(
    *,
    coverage: dict[str, Any],
    labels: list[dict[str, Any]],
    data_lake_root: Path | None,
) -> dict[str, dict[str, Any]]:
    local_extra = max(0, coverage["total_launches"] - 3_000)
    root_hint = str(data_lake_root) if data_lake_root else "/Volumes/ORICO/MemeTraderPro"
    return {
        "Existing local normalized events beyond current all-collected sample": {
            "classification": "usable_now" if local_extra else "blocked",
            "extra_launch_count_estimate": local_extra,
            "extra_unique_dates_estimate": 0,
            "confidence": "low" if not local_extra else "medium",
            "blockers": [] if local_extra else ["current lifecycle normalized all-collected sample remains the largest usable local snapshot set"],
        },
        "Raw launch census not yet included in all-collected sample": {
            "classification": "usable_with_enrichment",
            "extra_launch_count_estimate": "unknown_without_lifecycle_snapshots",
            "extra_unique_dates_estimate": "unknown",
            "confidence": "medium",
            "blockers": ["requires first-two-hour lifecycle and FDV-proxy enrichment before trigger reconstruction"],
        },
        "Pump.fun create-event census": {
            "classification": "usable_with_enrichment",
            "extra_launch_count_estimate": "potentially_large",
            "extra_unique_dates_estimate": "potentially_large",
            "confidence": "medium",
            "blockers": ["create rows alone do not provide $20k trigger features or forward path"],
        },
        "PumpSwap/Pump.fun transaction archives": {
            "classification": "usable_with_parser_repair",
            "extra_launch_count_estimate": "unknown",
            "extra_unique_dates_estimate": "unknown",
            "confidence": "low",
            "blockers": ["needs archive-specific parser and valuation reconstruction audit"],
        },
        "DexScreener pair detection records": {
            "classification": "usable_with_enrichment",
            "extra_launch_count_estimate": "limited_by_survivorship_bias",
            "extra_unique_dates_estimate": "unknown",
            "confidence": "medium",
            "blockers": ["survivorship bias; not enough for failed/pre-DexScreener launches"],
        },
        "Helius historical transaction fetch": {
            "classification": "needs_external_fetch",
            "recommended_method": "parallel_date_sharded_pull",
            "extra_launch_count_estimate": "target 1,000+ $20k trigger rows across 30+ dates",
            "extra_unique_dates_estimate": "30+",
            "expected_storage": "raw preserved by date shard; parsed snapshots compacted to parquet/jsonl",
            "expected_runtime": "materially faster than serial pull using bounded concurrent date shards and per-shard checkpointing",
            "expected_api_calls": "estimate after date-shard pilot; cap each shard before broad execution",
            "confidence": "high",
            "blockers": ["requires explicit external fetch approval and Helius credit/rate-limit caps"],
        },
        "DexScreener current/pair API": {
            "classification": "needs_external_fetch",
            "recommended_method": "future_observation_only_not_historical_backfill",
            "extra_launch_count_estimate": "not suitable for historical failed launch census",
            "extra_unique_dates_estimate": 0,
            "confidence": "high",
            "blockers": ["current API cannot reconstruct failed historical pre-pair launches reliably"],
        },
        "Other cached ORICO project files": {
            "classification": "usable_with_parser_repair",
            "searched_root": root_hint,
            "extra_launch_count_estimate": "unknown",
            "extra_unique_dates_estimate": "unknown",
            "confidence": "low",
            "blockers": ["needs targeted parser/source audit before counting as usable"],
        },
    }


def _acquisition_plan(
    sources: dict[str, dict[str, Any]],
    coverage: dict[str, Any],
    date_balance: dict[str, Any],
) -> dict[str, Any]:
    needed_rows = max(0, PREFERRED_TARGET["total_20k_rows"] - date_balance["total_rows"])
    needed_dates = max(0, PREFERRED_TARGET["unique_20k_dates"] - date_balance["unique_dates"])
    return {
        "recommended_path": "parallel Helius/Pump.fun historical acquisition by date shard",
        "why": "local all-collected sample remains too date-clustered for validation dominance gates",
        "target_gap": {
            "additional_20k_trigger_rows_needed": needed_rows,
            "additional_20k_trigger_dates_needed": needed_dates,
        },
        "parallel_pull_design": {
            "sharding": "one bounded worker group per target date or small date range",
            "worker_model": "parallel date shards with per-shard signature and transaction hydration workers",
            "checkpointing": "checkpoint raw signatures, hydrated transactions, parsed lifecycle rows, and date-level completion separately",
            "dedupe": "global signature and mint dedupe before snapshot construction",
            "caps": "cap launches/date and requests/date; stop if date balance target cannot improve",
            "preservation": "preserve raw Helius transactions under ORICO by date shard before parsing",
            "avoid_cluster_repeat": "select dates to cap top-date share and avoid adding more 2026-06-01 dominated rows",
        },
        "first_pilot": {
            "dates": "5-10 new target dates outside 2026-05-25, 2026-05-26, 2026-06-01",
            "goal": "prove trigger reconstruction and rows/date before scaling",
            "success": ">=10 $20k-trigger rows/date with >=90% forward path coverage",
        },
        "full_target": PREFERRED_TARGET,
        "do_not_run_yet": True,
    }


def _write_expanded_outputs(
    labels: list[dict[str, Any]],
    launch_rows: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    output_root: Path | str,
) -> dict[str, Path]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    launch_path = root / "expanded_launches.parquet"
    snapshots_path = root / "expanded_lifecycle_snapshots.parquet"
    labels_path = root / "expanded_trigger_labels.parquet"
    labels_jsonl = root / "expanded_trigger_labels.jsonl"
    _write_parquet([{k: v for k, v in row.items() if k != "priced_snapshots"} for row in launch_rows], launch_path)
    _write_parquet(snapshots, snapshots_path)
    _write_parquet(labels, labels_path)
    _write_jsonl(labels, labels_jsonl)
    return {
        "expanded_launches_parquet": launch_path,
        "expanded_lifecycle_snapshots_parquet": snapshots_path,
        "expanded_trigger_labels_parquet": labels_path,
        "expanded_trigger_labels_jsonl": labels_jsonl,
    }


def _write_reports(report: dict[str, Any], report_dir: Path | str) -> dict[str, Path]:
    output = Path(report_dir)
    output.mkdir(parents=True, exist_ok=True)
    audit_json = output / "historical_coverage_audit.json"
    audit_md = output / "historical_coverage_audit.md"
    summary_json = output / "historical_date_expansion_summary.json"
    summary_md = output / "historical_date_expansion_summary.md"
    plan_json = output / "historical_expansion_plan.json"
    audit_json.write_text(json.dumps(report["coverage_audit"], indent=2, sort_keys=True), encoding="utf-8")
    audit_md.write_text(_audit_markdown(report), encoding="utf-8")
    summary_json.write_text(json.dumps(_public_summary(report), indent=2, sort_keys=True), encoding="utf-8")
    summary_md.write_text(_summary_markdown(report), encoding="utf-8")
    plan_json.write_text(json.dumps(report["acquisition_plan"], indent=2, sort_keys=True), encoding="utf-8")
    return {
        "historical_coverage_audit_json": audit_json,
        "historical_coverage_audit_md": audit_md,
        "historical_date_expansion_summary_json": summary_json,
        "historical_date_expansion_summary_md": summary_md,
        "historical_expansion_plan_json": plan_json,
    }


def _public_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "expanded_trigger_labels"}


def _audit_markdown(report: dict[str, Any]) -> str:
    audit = report["coverage_audit"]
    return "\n".join(
        [
            "# Historical Coverage Audit",
            "",
            f"- Total launches: `{audit['total_launches']}`",
            f"- Date range: `{audit['date_range']}`",
            f"- Unique launch dates: `{audit['unique_launch_dates']}`",
            f"- $15k trigger rows: `{audit['trigger_counts']['15k']['total_rows']}`",
            f"- $20k trigger rows: `{audit['trigger_counts']['20k']['total_rows']}`",
            f"- $30k trigger rows: `{audit['trigger_counts']['30k']['total_rows']}`",
            f"- Forward path coverage from $20k: `{audit['forward_path_coverage']['20k']}`",
            "",
            "No thesis, validation, or trading logic was run.",
            "",
        ]
    )


def _summary_markdown(report: dict[str, Any]) -> str:
    balance = report["date_balance"]
    return "\n".join(
        [
            "# Historical Date Expansion Summary",
            "",
            f"- Readiness: `{report['readiness_classification']}`",
            f"- Previous $20k trigger dates: `{report['previous_20k_trigger_dates']}`",
            f"- Expanded $20k trigger dates: `{report['expanded_20k_trigger_dates']}`",
            f"- Previous $20k trigger rows: `{report['previous_20k_trigger_rows']}`",
            f"- Expanded $20k trigger rows: `{report['expanded_20k_trigger_rows']}`",
            f"- Median rows/date: `{balance['median_rows_per_active_date']}`",
            f"- Top date share: `{balance['top_date_share']}`",
            f"- Top 3 date share: `{balance['top3_date_share']}`",
            f"- Preferred target met: `{report['preferred_target_met']}`",
            f"- External acquisition required: `{report['external_acquisition_required']}`",
            "",
            "Next action: use the parallel date-sharded acquisition plan before rerunning winner anatomy or T011.",
            "",
        ]
    )


def _status_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Explosive Runner Historical Date Expansion Status",
            "",
            "## Why Expand Dates",
            "",
            "T011 validation failed because the selected holdout bucket was date-dominated. The project must broaden historical dates before rerunning winner anatomy, T011, robustness, or validation.",
            "",
            "## Current Limitation",
            "",
            "- Current $20k-trigger sample has only `3` unique dates.",
            "- The validation holdout was entirely `2026-06-01`.",
            "",
            "## Preferred Target",
            "",
            "- `30+` unique $20k-trigger dates",
            "- `1,000+` total $20k-trigger rows",
            "- median at least `10` rows per active date",
            "- no single date above `35%`",
            "- top 3 dates below `60%`",
            "- forward path coverage at least `90%`",
            "",
            "## Sources Audited",
            "",
            *[f"- {name}: `{payload['classification']}`" for name, payload in report["expansion_paths"].items()],
            "",
            "## Expansion Path Chosen",
            "",
            f"- `{report['acquisition_plan']['recommended_path']}`",
            "- Use the faster parallel date-sharded pull design. Do not run a slow serial acquisition for the next large pull.",
            "",
            "## Coverage Result",
            "",
            f"- Expanded $20k-trigger dates: `{report['expanded_20k_trigger_dates']}`",
            f"- Expanded $20k-trigger rows: `{report['expanded_20k_trigger_rows']}`",
            f"- Top date share: `{report['date_balance']['top_date_share']}`",
            f"- Top 3 date share: `{report['date_balance']['top3_date_share']}`",
            f"- Readiness: `{report['readiness_classification']}`",
            "",
            "## Outputs",
            "",
            *[f"- `{path}`" for path in report["report_paths"].values()],
            *[f"- `{path}`" for path in report["expanded_paths"].values()],
            "",
            "## Next Recommended Action",
            "",
            "Run a bounded external acquisition pilot using parallel date shards. Do not rerun winner anatomy, T011, or validation until the preferred date-balance target is met.",
            "",
        ]
    )


def _plan_markdown(report: dict[str, Any]) -> str:
    plan = report["acquisition_plan"]
    return "\n".join(
        [
            "# MemeTraderPro Explosive Runner Historical Expansion Plan",
            "",
            "## Decision",
            "",
            "Existing local data does not meet the preferred date-balance target. The next data acquisition should use parallel date-sharded pulls, not the previous slow serial approach.",
            "",
            "## Target Gap",
            "",
            f"- Additional $20k-trigger rows needed: `{plan['target_gap']['additional_20k_trigger_rows_needed']}`",
            f"- Additional $20k-trigger dates needed: `{plan['target_gap']['additional_20k_trigger_dates_needed']}`",
            "",
            "## Faster Parallel Pull Design",
            "",
            *[f"- {key}: `{value}`" for key, value in plan["parallel_pull_design"].items()],
            "",
            "## First Pilot",
            "",
            *[f"- {key}: `{value}`" for key, value in plan["first_pilot"].items()],
            "",
            "## Guardrails",
            "",
            "- Preserve raw transactions before parsing.",
            "- Cap requests per date shard.",
            "- Stop if date balance cannot improve.",
            "- Do not run thesis, validation, trading logic, optimization, grid search, or ML during acquisition.",
            "",
        ]
    )


def _date_balance_met(balance: dict[str, Any]) -> bool:
    return (
        balance["unique_dates"] >= PREFERRED_TARGET["unique_20k_dates"]
        and balance["total_rows"] >= PREFERRED_TARGET["total_20k_rows"]
        and (balance["median_rows_per_active_date"] or 0) >= PREFERRED_TARGET["median_rows_per_date"]
        and (balance["top_date_share"] or 0) <= PREFERRED_TARGET["max_top_date_share"]
        and (balance["top3_date_share"] or 0) < PREFERRED_TARGET["max_top3_date_share"]
    )


def _trigger_count_by_date(labels: list[dict[str, Any]], field: str) -> dict[str, Any]:
    counts = Counter(row["launch_date"] for row in labels if row.get(field))
    return {"total_rows": sum(counts.values()), "by_date": dict(sorted(counts.items()))}


def _milestone_count_by_date(labels: list[dict[str, Any]], field: str) -> dict[str, Any]:
    counts = Counter(row["launch_date"] for row in labels if row.get(field))
    return {"total_rows": sum(counts.values()), "by_date": dict(sorted(counts.items()))}


def _tier_counts(labels: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(_tier(row) for row in labels if row.get("trigger_20k_time")))


def _tier(row: dict[str, Any]) -> str:
    if row.get("crossed_1m"):
        return "reached_1m_plus"
    if row.get("crossed_500k"):
        return "reached_500k_but_never_1m"
    if row.get("crossed_200k"):
        return "reached_200k_but_never_500k"
    if row.get("crossed_100k"):
        return "reached_100k_but_never_200k"
    if row.get("crossed_50k"):
        return "reached_50k_but_never_100k"
    return "reached_20k_but_never_50k"


def _forward_coverage_rate(labels: list[dict[str, Any]]) -> float:
    trigger = [row for row in labels if row.get("trigger_20k_time")]
    return _ratio(sum(1 for row in trigger if row.get("forward_path_coverage")), len(trigger)) or 0


def _coverage(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    scoped = [row for row in rows if row.get("trigger_20k_time")]
    available = sum(1 for row in scoped if row.get(field) is not None)
    return {"available_rows": available, "missing_rows": len(scoped) - available, "coverage_pct": (_ratio(available, len(scoped)) or 0) * 100}


def _date_range(counts: Counter) -> dict[str, Any]:
    dates = sorted(date for date in counts if date)
    return {"start": dates[0] if dates else None, "end": dates[-1] if dates else None}


def _first_crossing(rows: list[dict[str, Any]], threshold: float) -> dict[str, Any] | None:
    return next((row for row in rows if (_value(row) or 0) >= threshold), None)


def _crossing_time(rows: list[dict[str, Any]], threshold: float) -> int | None:
    row = _first_crossing(rows, threshold)
    return _int_or_none(row.get("snapshot_ts")) if row else None


def _time_delta_from_trigger(rows: list[dict[str, Any]], trigger: dict[str, Any] | None, threshold: float) -> int | None:
    if not trigger:
        return None
    crossed = _first_crossing(rows, threshold)
    if not crossed:
        return None
    return _age(crossed) - _age(trigger)


def _forward_path_coverage(rows: list[dict[str, Any]], trigger: dict[str, Any] | None) -> bool:
    if not trigger:
        return False
    return any(_age(row) >= _age(trigger) for row in rows)


def _creator(rows: list[dict[str, Any]]) -> str | None:
    for row in rows:
        meta = row.get("metadata_json") or {}
        if meta.get("creator_deployer"):
            return meta.get("creator_deployer")
        if row.get("creator"):
            return row.get("creator")
    return None


def _write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


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


def _date_key(timestamp: int | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")


def _ratio(a: Any, b: Any) -> float | None:
    av = _float_or_none(a)
    bv = _float_or_none(b)
    if av is None or bv in (None, 0):
        return None
    return av / bv


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
