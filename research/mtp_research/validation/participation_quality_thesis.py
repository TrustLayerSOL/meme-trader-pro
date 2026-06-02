"""Descriptive T006 participation quality thesis cycle."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from research.mtp_research.validation.robust_return_metrics import winsorized_mean


THESIS_ID = "T006"
THESIS_NAME = "Participation Quality"
SNAPSHOT_AGES = {"30s": 30, "1m": 60, "3m": 180, "5m": 300, "10m": 600, "30m": 1800}
LIQUIDITY_AGES = {"3m": 180, "10m": 600, "30m": 1800}
EVENTS_PER_ACTIVE_WALLET_FEATURES = [f"events_per_active_wallet_{label}" for label in SNAPSHOT_AGES]
EVENTS_PER_UNIQUE_ACTOR_FEATURES = [f"events_per_unique_actor_{label}" for label in SNAPSHOT_AGES]
BUYS_PER_ACTIVE_WALLET_FEATURES = [f"buys_per_active_wallet_{label}" for label in SNAPSHOT_AGES]
SELLS_PER_ACTIVE_WALLET_FEATURES = [f"sells_per_active_wallet_{label}" for label in SNAPSHOT_AGES]
ACTIVE_WALLETS_PER_EVENT_FEATURES = [f"active_wallets_per_event_{label}" for label in SNAPSHOT_AGES]
UNIQUE_ACTORS_PER_EVENT_FEATURES = [f"unique_actors_per_event_{label}" for label in SNAPSHOT_AGES]
LIQUIDITY_NORMALIZED_FEATURES = [
    *[f"active_wallets_per_liquidity_proxy_{label}" for label in LIQUIDITY_AGES],
    *[f"unique_actors_per_liquidity_proxy_{label}" for label in LIQUIDITY_AGES],
    *[f"event_count_per_liquidity_proxy_{label}" for label in LIQUIDITY_AGES],
]
INTENSITY_PROXY_FEATURES = [
    "event_intensity_per_actor_3m",
    "event_intensity_per_actor_10m",
    "event_intensity_per_actor_30m",
    "buy_intensity_per_actor_3m",
    "sell_intensity_per_actor_3m",
]
FEATURES = [
    *EVENTS_PER_ACTIVE_WALLET_FEATURES,
    *EVENTS_PER_UNIQUE_ACTOR_FEATURES,
    *BUYS_PER_ACTIVE_WALLET_FEATURES,
    *SELLS_PER_ACTIVE_WALLET_FEATURES,
    *ACTIVE_WALLETS_PER_EVENT_FEATURES,
    *UNIQUE_ACTORS_PER_EVENT_FEATURES,
    *LIQUIDITY_NORMALIZED_FEATURES,
    *INTENSITY_PROXY_FEATURES,
]
FIELD_AUDIT_FIELDS = [
    "launch_id",
    "mint",
    "block_time",
    "snapshot label / snapshot age",
    "buy_count",
    "sell_count",
    "event_count",
    "active_wallets",
    "unique_actors",
    "liquidity_proxy",
    "FDV-proxy runup",
    "FDV-proxy drawdown",
    "120m price availability",
    "120m liquidity-proxy availability",
]
ALLOWED_CLASSIFICATIONS = {"descriptive_signal_present", "weak_signal", "no_signal", "data_limited"}


def build_t006_participation_quality_report(
    *,
    snapshots_path: Path | str,
    outcomes_path: Path | str,
    bucket_count: int = 5,
) -> dict[str, Any]:
    snapshots = _read_jsonl(snapshots_path)
    outcomes_by_mint = {row["token_mint"]: row for row in _read_jsonl(outcomes_path)}
    snapshots_by_mint = _group_by_mint(snapshots)
    launch_rows = [
        _build_launch_row(mint=mint, snapshots=rows, outcome=outcomes_by_mint.get(mint, {}))
        for mint, rows in sorted(snapshots_by_mint.items())
    ]
    launch_rows = sorted(launch_rows, key=lambda row: (row.get("launch_ts") or 0, row["token_mint"]))
    field_audit = _field_coverage_audit(snapshots, launch_rows)
    feature_reports = {feature: _feature_report(launch_rows, feature, bucket_count) for feature in FEATURES}
    warning_flags = _warning_flags(launch_rows, field_audit)
    classification = _classify(launch_rows, feature_reports, warning_flags)
    return {
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "research_question": (
            "Do launches with healthier participation quality, measured as deterministic activity-per-actor "
            "and breadth-per-activity ratios, show better FDV-proxy lifecycle outcomes?"
        ),
        "hypothesis": (
            "Participation quality ratios may explain whether weak participation and flow signals are simple "
            "activity effects or broader actor-quality effects."
        ),
        "dataset": {
            "snapshots_path": str(snapshots_path),
            "outcomes_path": str(outcomes_path),
            "launch_count": len(launch_rows),
            "snapshot_count": len(snapshots),
            "strict_launch_regime": True,
            "valuation_semantics": "fdv_proxy_only",
            "true_market_cap_claims": "blocked",
        },
        "methodology": {
            "bucket_method": "deterministic_rank_quantile_buckets",
            "bucket_count": bucket_count,
            "snapshot_ages_seconds": SNAPSHOT_AGES,
            "candidate_features": FEATURES,
            "classification_options": sorted(ALLOWED_CLASSIFICATIONS),
        },
        "methodology_flags": [
            "research_only",
            "no_trading_rules",
            "no_profitability_claims",
            "no_entry_exit_logic",
            "no_threshold_optimization",
            "no_grid_search",
            "no_ml_black_boxes",
            "no_future_leakage",
            "fdv_proxy_not_true_market_cap",
        ],
        "methodology_checks": [
            "deterministic_outputs",
            "threshold_tuning_absent",
            "independent_feature_reviews",
            "median_only_primary_summaries",
        ],
        "feature_semantics": _feature_semantics(),
        "field_coverage_audit": field_audit,
        "launch_rows": launch_rows,
        "sample_counts": _sample_counts(launch_rows),
        "outcome_coverage": _outcome_coverage(launch_rows),
        "missing_value_audit": _missing_value_audit(launch_rows),
        "feature_reports": feature_reports,
        "sensitivity_checks": _sensitivity_checks(launch_rows, feature_reports),
        "prior_cycle_comparison": {
            "T001": "no_signal",
            "T002": "weak_signal",
            "T003": "no_signal",
            "T004": "no_signal",
            "T005": "weak_signal",
            "T006": classification,
            "comparison_note": (
                "Qualitative comparison only. T006 checks whether participation ratios add descriptive "
                "structure beyond raw T005 activity counts."
            ),
        },
        "final_classification": classification,
        "warning_flags": warning_flags,
        "limitations": _limitations(warning_flags),
        "next_recommendation": _next_recommendation(classification, warning_flags),
        "reproducible_command": _reproducible_command(snapshots_path, outcomes_path, bucket_count),
    }


def write_t006_report_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "T006_participation_quality_summary.json"
    markdown_path = output / "T006_participation_quality_summary.md"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": markdown_path, "status_path": status}


def _build_launch_row(*, mint: str, snapshots: list[dict[str, Any]], outcome: dict[str, Any]) -> dict[str, Any]:
    ordered = sorted(snapshots, key=lambda row: int(row.get("launch_age_seconds", 0)))
    by_age = {int(row.get("launch_age_seconds", 0)): row for row in ordered}
    return {
        "launch_id": _first_present(*(row.get("launch_id") for row in ordered)),
        "token_mint": mint,
        "mint": mint,
        "launch_ts": _int_or_none(_first_present(*(row.get("launch_ts") for row in ordered))),
        "snapshot_ages": sorted(by_age),
        "features": _build_features(by_age),
        "outcomes": _fdv_outcomes(ordered, outcome),
        "metadata_json": {
            "feature_window": "first_30m",
            "available_snapshot_ages": sorted(by_age),
            "max_feature_snapshot_age_seconds": max((age for age in SNAPSHOT_AGES.values() if age in by_age), default=None),
        },
    }


def _build_features(by_age: dict[int, dict[str, Any]]) -> dict[str, Any]:
    features: dict[str, Any] = {}
    for label, age in SNAPSHOT_AGES.items():
        snapshot = by_age.get(age)
        buys = _field_value(snapshot, "buy_count")
        sells = _field_value(snapshot, "sell_count")
        events = _event_count(snapshot)
        active_wallets = _field_value(snapshot, "active_wallets")
        unique_actors = _field_value(snapshot, "unique_actors")
        features[f"events_per_active_wallet_{label}"] = _ratio(events, active_wallets)
        features[f"events_per_unique_actor_{label}"] = _ratio(events, unique_actors)
        features[f"buys_per_active_wallet_{label}"] = _ratio(buys, active_wallets)
        features[f"sells_per_active_wallet_{label}"] = _ratio(sells, active_wallets)
        features[f"active_wallets_per_event_{label}"] = _ratio(active_wallets, events)
        features[f"unique_actors_per_event_{label}"] = _ratio(unique_actors, events)
    for label, age in LIQUIDITY_AGES.items():
        snapshot = by_age.get(age)
        liquidity = _field_value(snapshot, "liquidity_proxy")
        features[f"active_wallets_per_liquidity_proxy_{label}"] = _ratio(_field_value(snapshot, "active_wallets"), liquidity)
        features[f"unique_actors_per_liquidity_proxy_{label}"] = _ratio(_field_value(snapshot, "unique_actors"), liquidity)
        features[f"event_count_per_liquidity_proxy_{label}"] = _ratio(_event_count(snapshot), liquidity)
        features[f"event_intensity_per_actor_{label}"] = _ratio(_event_count(snapshot), _field_value(snapshot, "unique_actors"))
    snapshot_3m = by_age.get(180)
    features["buy_intensity_per_actor_3m"] = _ratio(_field_value(snapshot_3m, "buy_count"), _field_value(snapshot_3m, "unique_actors"))
    features["sell_intensity_per_actor_3m"] = _ratio(_field_value(snapshot_3m, "sell_count"), _field_value(snapshot_3m, "unique_actors"))
    return features


def _fdv_outcomes(snapshots: list[dict[str, Any]], outcome: dict[str, Any]) -> dict[str, Any]:
    values = [
        _float_or_none(row.get("valuation_proxy_usd"))
        for row in snapshots
        if row.get("valuation_proxy_available") and _float_or_none(row.get("valuation_proxy_usd")) is not None
    ]
    values = [value for value in values if value is not None]
    if values and values[0] not in (None, 0):
        base = values[0]
        runup = (max(values) / base) - 1
        drawdown = (min(values) / base) - 1
        ret = (values[-1] / base) - 1
    else:
        runup = None
        drawdown = None
        ret = None
    return {
        "fdv_proxy_runup_120m": runup,
        "fdv_proxy_drawdown_120m": drawdown,
        "fdv_proxy_return_120m": ret,
        "price_available_120m": bool(outcome.get("price_available_120m") or outcome.get("has_price_at_120m")),
        "liquidity_proxy_available_120m": bool(
            outcome.get("has_liquidity_proxy_at_120m") or outcome.get("liquidity_survival_120m")
        ),
        "true_market_cap_available": bool(outcome.get("true_market_cap_available")),
    }


def _field_coverage_audit(snapshots: list[dict[str, Any]], launch_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    snapshot_total = len(snapshots)
    launch_total = len(launch_rows)
    checks = {
        "launch_id": (snapshot_total, sum(1 for row in snapshots if row.get("launch_id"))),
        "mint": (snapshot_total, sum(1 for row in snapshots if row.get("token_mint"))),
        "block_time": (snapshot_total, sum(1 for row in snapshots if row.get("snapshot_ts") or row.get("launch_ts"))),
        "snapshot label / snapshot age": (snapshot_total, sum(1 for row in snapshots if row.get("launch_age_seconds") is not None)),
        "buy_count": (snapshot_total, sum(1 for row in snapshots if _float_or_none(row.get("buy_count")) is not None)),
        "sell_count": (snapshot_total, sum(1 for row in snapshots if _float_or_none(row.get("sell_count")) is not None)),
        "event_count": (snapshot_total, sum(1 for row in snapshots if _event_count(row) is not None)),
        "active_wallets": (snapshot_total, sum(1 for row in snapshots if _float_or_none(row.get("active_wallets")) is not None)),
        "unique_actors": (snapshot_total, sum(1 for row in snapshots if _float_or_none(row.get("unique_actors")) is not None)),
        "liquidity_proxy": (snapshot_total, sum(1 for row in snapshots if _float_or_none(row.get("liquidity_proxy")) is not None)),
        "FDV-proxy runup": (launch_total, sum(1 for row in launch_rows if row["outcomes"].get("fdv_proxy_runup_120m") is not None)),
        "FDV-proxy drawdown": (launch_total, sum(1 for row in launch_rows if row["outcomes"].get("fdv_proxy_drawdown_120m") is not None)),
        "120m price availability": (launch_total, sum(1 for row in launch_rows if row["outcomes"].get("price_available_120m"))),
        "120m liquidity-proxy availability": (launch_total, sum(1 for row in launch_rows if row["outcomes"].get("liquidity_proxy_available_120m"))),
    }
    return {
        field: {
            "available_rows": available,
            "missing_rows": total - available,
            "coverage_pct": (available / total * 100) if total else 0,
            "denominator": total,
            "semantics": _field_semantics().get(field, "deterministic field coverage"),
        }
        for field, (total, available) in checks.items()
    }


def _field_semantics() -> dict[str, str]:
    return {
        "launch_id": "launch identifier carried from the lifecycle artifact",
        "mint": "token_mint from strict launch-regime snapshots",
        "block_time": "launch_ts or snapshot_ts, not a future outcome field",
        "snapshot label / snapshot age": "launch_age_seconds in the first two-hour lifecycle grid",
        "buy_count": "cumulative classified buy count at the snapshot age",
        "sell_count": "cumulative classified sell count at the snapshot age",
        "event_count": "cumulative lifecycle event count at the snapshot age",
        "active_wallets": "observed active wallets in the lifecycle snapshot",
        "unique_actors": "observed unique actors in the lifecycle snapshot",
        "liquidity_proxy": "bonding-curve reserve proxy, not confirmed DEX depth",
        "FDV-proxy runup": "first-two-hour valuation-proxy runup from enriched snapshots",
        "FDV-proxy drawdown": "first-two-hour valuation-proxy drawdown from enriched snapshots",
        "120m price availability": "price snapshot availability at 120m",
        "120m liquidity-proxy availability": "liquidity proxy availability at 120m",
    }


def _feature_semantics() -> dict[str, str]:
    return {
        "events_per_active_wallet": "event_count divided by active_wallets at the same launch-relative age",
        "events_per_unique_actor": "event_count divided by unique_actors at the same launch-relative age",
        "buys_per_active_wallet": "buy_count divided by active_wallets at the same launch-relative age",
        "sells_per_active_wallet": "sell_count divided by active_wallets at the same launch-relative age",
        "active_wallets_per_event": "active_wallets divided by event_count at the same launch-relative age",
        "unique_actors_per_event": "unique_actors divided by event_count at the same launch-relative age",
        "liquidity_normalized_participation": "actor or event count divided by bonding-curve reserve proxy",
        "event_intensity_per_actor": "event_count divided by unique_actors; this is an intensity proxy only",
        "buy_intensity_per_actor": "buy_count divided by unique_actors; this is an intensity proxy only",
        "sell_intensity_per_actor": "sell_count divided by unique_actors; this is an intensity proxy only",
    }


def _feature_report(rows: list[dict[str, Any]], feature: str, bucket_count: int) -> dict[str, Any]:
    usable = [row for row in rows if _feature_value(row, feature) is not None]
    values = [_feature_value(row, feature) for row in usable]
    values = [value for value in values if value is not None]
    buckets = _bucket_tables(usable, feature, bucket_count)
    return {
        "feature": feature,
        "sample_count": len(rows),
        "usable_count": len(usable),
        "missing_count": len(rows) - len(usable),
        "bucket_count": len(buckets),
        "quantile_definitions": "deterministic rank buckets over non-missing values",
        "distribution_summary": _distribution_summary(values),
        "bucket_tables": buckets,
        "median_only_summary": _outcome_summary(usable),
        "outlier_adjusted_summary": {
            "winsorized_mean_fdv_proxy_runup_120m": winsorized_mean(
                [_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in usable]
            ),
            "winsorized_mean_fdv_proxy_drawdown_120m": winsorized_mean(
                [_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in usable]
            ),
        },
    }


def _bucket_tables(rows: list[dict[str, Any]], feature: str, bucket_count: int) -> list[dict[str, Any]]:
    usable = sorted(rows, key=lambda row: (_feature_value(row, feature), row.get("launch_ts") or 0, row["token_mint"]))
    if not usable:
        return []
    buckets = [[] for _ in range(min(bucket_count, len(usable)))]
    for index, row in enumerate(usable):
        bucket_index = min(len(buckets) - 1, int(index * len(buckets) / len(usable)))
        buckets[bucket_index].append(row)
    return [_summarize_bucket(feature, index + 1, bucket) for index, bucket in enumerate(buckets)]


def _summarize_bucket(feature: str, bucket_number: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_feature_value(row, feature) for row in rows]
    values = [value for value in values if value is not None]
    summary = _outcome_summary(rows)
    summary.update(
        {
            "bucket": f"q{bucket_number}",
            "feature_min": min(values) if values else None,
            "feature_max": max(values) if values else None,
        }
    )
    return summary


def _outcome_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    runups = [_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in rows]
    drawdowns = [_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in rows]
    return {
        "sample_count": len(rows),
        "token_count": len({row["token_mint"] for row in rows}),
        "median_fdv_proxy_runup_120m": _median(runups),
        "median_fdv_proxy_drawdown_120m": _median(drawdowns),
        "price_available_120m_rate": _true_rate(row["outcomes"].get("price_available_120m") for row in rows),
        "liquidity_proxy_available_120m_rate": _true_rate(row["outcomes"].get("liquidity_proxy_available_120m") for row in rows),
    }


def _sample_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"launch_count": len(rows), "token_count": len({row["token_mint"] for row in rows})}


def _outcome_coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "fdv_proxy_runup_available": sum(1 for row in rows if row["outcomes"].get("fdv_proxy_runup_120m") is not None),
        "fdv_proxy_drawdown_available": sum(1 for row in rows if row["outcomes"].get("fdv_proxy_drawdown_120m") is not None),
        "price_available_120m": sum(1 for row in rows if row["outcomes"].get("price_available_120m")),
        "liquidity_proxy_available_120m": sum(1 for row in rows if row["outcomes"].get("liquidity_proxy_available_120m")),
    }


def _missing_value_audit(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        feature: {
            "available_count": len(rows) - (missing := sum(1 for row in rows if _feature_value(row, feature) is None)),
            "missing_count": missing,
            "missing_rate": (missing / len(rows)) if rows else None,
        }
        for feature in FEATURES
    }


def _sensitivity_checks(rows: list[dict[str, Any]], feature_reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    runups = sorted(
        value for value in (_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in rows)
        if value is not None
    )
    drawdowns = sorted(
        value for value in (_float_or_none(row["outcomes"].get("fdv_proxy_drawdown_120m")) for row in rows)
        if value is not None
    )
    participation_values = sorted(
        value for value in (_feature_value(row, "events_per_unique_actor_30m") for row in rows)
        if value is not None
    )
    runup_p99 = _quantile(runups, 0.99)
    drawdown_p01 = _quantile(drawdowns, 0.01)
    participation_p99 = _quantile(participation_values, 0.99)
    return {
        "bucket_count_audit": {
            feature: {
                "bucket_count": report["bucket_count"],
                "min_bucket_size": min((bucket["sample_count"] for bucket in report["bucket_tables"]), default=0),
            }
            for feature, report in feature_reports.items()
        },
        "tiny_bucket_features": [
            feature for feature, report in feature_reports.items()
            if report["bucket_tables"] and min(bucket["sample_count"] for bucket in report["bucket_tables"]) < 25
        ],
        "exclude_extreme_fdv_proxy_runups": _outcome_summary(
            [row for row in rows if runup_p99 is None or (row["outcomes"].get("fdv_proxy_runup_120m") or 0) <= runup_p99]
        ),
        "exclude_extreme_fdv_proxy_drawdowns": _outcome_summary(
            [row for row in rows if drawdown_p01 is None or (row["outcomes"].get("fdv_proxy_drawdown_120m") or 0) >= drawdown_p01]
        ),
        "exclude_extreme_participation_quality_values": _outcome_summary(
            [row for row in rows if participation_p99 is None or (_feature_value(row, "events_per_unique_actor_30m") or 0) <= participation_p99]
        ),
    }


def _warning_flags(rows: list[dict[str, Any]], field_audit: dict[str, dict[str, Any]]) -> list[str]:
    warnings = ["true_market_cap_claims_blocked", "intensity_proxy_not_direct_manipulation_evidence"]
    for field in ("buy_count", "sell_count", "event_count", "active_wallets", "unique_actors"):
        if field_audit[field]["missing_rows"]:
            warnings.append(f"{field}_missing")
    if field_audit["FDV-proxy runup"]["missing_rows"] or field_audit["FDV-proxy drawdown"]["missing_rows"]:
        warnings.append("fdv_proxy_outcomes_missing")
    if not rows:
        warnings.append("empty_dataset")
    return warnings


def _classify(rows: list[dict[str, Any]], feature_reports: dict[str, dict[str, Any]], warning_flags: list[str]) -> str:
    if len(rows) < 100 or "fdv_proxy_outcomes_missing" in warning_flags:
        return "data_limited"
    primary = [
        feature_reports["events_per_unique_actor_3m"],
        feature_reports["events_per_unique_actor_30m"],
        feature_reports["active_wallets_per_event_10m"],
        feature_reports["unique_actors_per_event_30m"],
        feature_reports["event_count_per_liquidity_proxy_30m"],
    ]
    signals = 0
    usable = 0
    for report in primary:
        buckets = report["bucket_tables"]
        if len(buckets) < 2:
            continue
        usable += 1
        low = buckets[0]["median_fdv_proxy_runup_120m"]
        high = buckets[-1]["median_fdv_proxy_runup_120m"]
        if low is not None and high is not None and high > low:
            signals += 1
    if usable == 0:
        return "data_limited"
    if signals >= 4:
        return "descriptive_signal_present"
    if signals >= 1:
        return "weak_signal"
    return "no_signal"


def _limitations(warning_flags: list[str]) -> list[str]:
    limitations = [
        "T006 is descriptive only and does not produce trading rules.",
        "Participation quality ratios are proxies derived from lifecycle snapshots, not identity-resolved holder state.",
        "Intensity proxy features are not direct evidence of manipulation or wash trading.",
        "FDV proxy is not true market cap because circulating supply is unavailable.",
    ]
    if any(flag.endswith("_missing") for flag in warning_flags):
        limitations.append("Some required snapshot fields are missing and were excluded feature-by-feature.")
    return limitations


def _next_recommendation(classification: str, warning_flags: list[str]) -> str:
    if any(flag.endswith("_missing") for flag in warning_flags):
        return "repair participation snapshot coverage before rerunning T006"
    if classification in {"descriptive_signal_present", "weak_signal"}:
        return "compare participation-quality ratios against raw T005 flow counts in a later preregistered robustness pass"
    return "treat participation quality as descriptive-only and continue testing non-flow thesis families"


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    public = dict(report)
    public.pop("launch_rows", None)
    return public


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# T006 Participation Quality",
        "",
        f"- Final classification: `{report['final_classification']}`",
        f"- Launch count: `{report['sample_counts']['launch_count']}`",
        f"- Warning flags: `{report['warning_flags']}`",
        "- Framing: descriptive research only",
        "",
        "## Feature Coverage Audit",
        "",
        "| Field | Available Rows | Missing Rows | Coverage | Semantics |",
        "|---|---:|---:|---:|---|",
    ]
    for field, audit in report["field_coverage_audit"].items():
        lines.append(
            f"| `{field}` | {audit['available_rows']} | {audit['missing_rows']} | "
            f"{audit['coverage_pct']:.2f}% | {audit['semantics']} |"
        )
    lines.extend(["", "## Median Outcome Tables", ""])
    for feature, feature_report in report["feature_reports"].items():
        lines.extend(
            [
                f"### `{feature}`",
                "",
                "| Bucket | Samples | Feature Min | Feature Max | Median FDV Runup | Median FDV Drawdown | Price 120m | Liquidity 120m |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for bucket in feature_report["bucket_tables"]:
            lines.append(
                f"| {bucket['bucket']} | {bucket['sample_count']} | {_format_num(bucket['feature_min'])} | "
                f"{_format_num(bucket['feature_max'])} | {_format_pct(bucket['median_fdv_proxy_runup_120m'])} | "
                f"{_format_pct(bucket['median_fdv_proxy_drawdown_120m'])} | {_format_pct(bucket['price_available_120m_rate'])} | "
                f"{_format_pct(bucket['liquidity_proxy_available_120m_rate'])} |"
            )
        if not feature_report["bucket_tables"]:
            lines.append("| n/a | 0 | n/a | n/a | n/a | n/a | n/a | n/a |")
        lines.append("")
    lines.extend(
        [
            "## Robustness Checks",
            "",
            f"- Tiny bucket features: `{report['sensitivity_checks']['tiny_bucket_features']}`",
            "- Extreme FDV-proxy and participation-quality exclusions are included in the JSON summary.",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Reproducible Command",
            "",
            "```bash",
            report["reproducible_command"],
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    return "\n".join(
        [
            "# T006 Participation Quality Status",
            "",
            "## Thesis Description",
            "",
            "Do participation-quality ratios add descriptive information beyond raw activity and flow counts?",
            "",
            "## Dataset Used",
            "",
            "- Strict launch-regime FDV-proxy lifecycle dataset",
            f"- Launches analyzed: `{report['sample_counts']['launch_count']}`",
            "",
            "## Feature Coverage",
            "",
            *[f"- `{field}`: `{audit['coverage_pct']:.2f}%`" for field, audit in report["field_coverage_audit"].items()],
            "",
            "## Outcome Coverage",
            "",
            *[f"- `{key}`: `{value}`" for key, value in report["outcome_coverage"].items()],
            "",
            "## Classification",
            "",
            f"`{report['final_classification']}`",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report["limitations"]],
            "",
            "## Comparison To T001-T005",
            "",
            *[f"- `{key}`: `{value}`" for key, value in report["prior_cycle_comparison"].items()],
            "",
            "## True Market-Cap Blocked Warning",
            "",
            "True market-cap claims remain blocked; this report uses FDV proxy only.",
            "",
            "## Next Recommendation",
            "",
            report["next_recommendation"],
            "",
            f"- Markdown summary: `{markdown_path}`",
            f"- JSON summary: `{json_path}`",
            "- No trading rules were generated.",
            "- No profitability claims were generated.",
            "- True market-cap claims remain blocked.",
            "",
        ]
    )


def _reproducible_command(snapshots_path: Path | str, outcomes_path: Path | str, bucket_count: int) -> str:
    return (
        "./trading_env/bin/python -m research.mtp_research.validation.run_participation_quality_thesis "
        f"--snapshots-path \"{snapshots_path}\" "
        f"--outcomes-path \"{outcomes_path}\" "
        f"--bucket-count {bucket_count}"
    )


def _field_value(row: dict[str, Any] | None, field: str) -> float | None:
    if not row:
        return None
    value = row.get(field)
    if value is None:
        value = (row.get("metadata_json") or {}).get(field)
    return _float_or_none(value)


def _event_count(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    value = _field_value(row, "event_count")
    if value is None:
        value = _field_value(row, "tx_count")
    return value


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _feature_value(row: dict[str, Any], feature: str) -> float | None:
    return _float_or_none(row["features"].get(feature))


def _distribution_summary(values: list[float]) -> dict[str, Any]:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None}
    return {
        "count": len(clean),
        "min": clean[0],
        "p25": _quantile(clean, 0.25),
        "median": median(clean),
        "p75": _quantile(clean, 0.75),
        "max": clean[-1],
        "mean": mean(clean),
    }


def _read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _group_by_mint(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        mint = row.get("token_mint")
        if mint:
            grouped[str(mint)].append(row)
    return grouped


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _median(values: list[float | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return median(clean) if clean else None


def _true_rate(values) -> float | None:
    clean = list(values)
    if not clean:
        return None
    return sum(1 for value in clean if value) / len(clean)


def _quantile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    index = min(len(values) - 1, max(0, round((len(values) - 1) * pct)))
    return values[index]


def _format_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _format_num(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"
