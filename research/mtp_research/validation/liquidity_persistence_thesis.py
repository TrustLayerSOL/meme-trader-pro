"""Descriptive T004 liquidity-persistence / depth-proxy thesis cycle."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from research.mtp_research.validation.robust_return_metrics import winsorized_mean


THESIS_ID = "T004"
THESIS_NAME = "Liquidity Persistence / Depth Proxy"
SNAPSHOT_AGES = {
    "30s": 30,
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "10m": 600,
    "30m": 1800,
    "120m": 7200,
}
LEVEL_FEATURES = [f"liquidity_proxy_{label}" for label in SNAPSHOT_AGES]
PERSISTENCE_FEATURES = [
    "liquidity_proxy_retention_30s_to_10m",
    "liquidity_proxy_retention_30s_to_30m",
    "liquidity_proxy_retention_3m_to_30m",
    "liquidity_proxy_retention_10m_to_120m",
    "liquidity_proxy_drop_30s_to_30m",
    "liquidity_proxy_drop_10m_to_120m",
]
TRAJECTORY_FEATURES = [
    "liquidity_proxy_growth_30s_to_3m",
    "liquidity_proxy_growth_3m_to_10m",
    "liquidity_proxy_growth_10m_to_30m",
    "liquidity_proxy_growth_30m_to_120m",
    "liquidity_proxy_slope_30s_to_30m",
]
INTERACTION_FEATURES = [
    "liquidity_per_active_wallet_30m",
    "liquidity_per_unique_actor_30m",
    "liquidity_per_event_30m",
    "liquidity_per_buy_30m",
    "liquidity_per_sell_30m",
]
FEATURES = LEVEL_FEATURES + PERSISTENCE_FEATURES + TRAJECTORY_FEATURES + INTERACTION_FEATURES
FIELD_AUDIT_FIELDS = [
    "launch_id",
    "mint",
    "block_time",
    "snapshot age / snapshot label",
    "liquidity_proxy",
    "bonding_curve_post_balance",
    "price/FDV proxy fields",
    "120m liquidity-proxy availability",
    "120m price availability",
    "FDV-proxy runup",
    "FDV-proxy drawdown",
]
ALLOWED_CLASSIFICATIONS = {
    "descriptive_signal_present",
    "weak_signal",
    "no_signal",
    "data_limited",
}


def build_t004_liquidity_persistence_report(
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
    missing_value_audit = _missing_value_audit(launch_rows)
    feature_reports = {feature: _feature_report(launch_rows, feature, bucket_count) for feature in FEATURES}
    warning_flags = _warning_flags(launch_rows, field_audit)
    classification = _classify(launch_rows, feature_reports, warning_flags)
    return {
        "thesis_id": THESIS_ID,
        "thesis_name": THESIS_NAME,
        "research_question": (
            "Do launches with stronger early liquidity-proxy persistence and healthier "
            "liquidity trajectory have better FDV-proxy lifecycle outcomes?"
        ),
        "hypothesis": (
            "Launches with stronger early bonding-curve liquidity-proxy persistence may "
            "show healthier FDV-proxy lifecycle outcomes."
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
        "liquidity_proxy_semantics": _liquidity_proxy_semantics(snapshots),
        "field_coverage_audit": field_audit,
        "launch_rows": launch_rows,
        "sample_counts": _sample_counts(launch_rows),
        "outcome_coverage": _outcome_coverage(launch_rows),
        "missing_value_audit": missing_value_audit,
        "feature_reports": feature_reports,
        "sensitivity_checks": _sensitivity_checks(launch_rows, feature_reports),
        "prior_cycle_comparison": {
            "T001": "no_signal",
            "T002": "weak_signal",
            "T003": "no_signal",
            "T004": classification,
            "comparison_note": "Qualitative comparison only; no thesis promotion is made.",
        },
        "final_classification": classification,
        "warning_flags": warning_flags,
        "limitations": _limitations(warning_flags),
        "next_recommendation": _next_recommendation(classification, warning_flags),
        "reproducible_command": _reproducible_command(snapshots_path, outcomes_path, bucket_count),
    }


def write_t004_report_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path | str,
    status_path: Path | str,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "T004_liquidity_persistence_summary.json"
    markdown_path = output / "T004_liquidity_persistence_summary.md"
    json_path.write_text(json.dumps(_public_report(report), indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_markdown_summary(report), encoding="utf-8")
    status = Path(status_path)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text(_status_markdown(report, markdown_path, json_path), encoding="utf-8")
    return {"json_summary_path": json_path, "markdown_summary_path": markdown_path, "status_path": status}


def _build_launch_row(*, mint: str, snapshots: list[dict[str, Any]], outcome: dict[str, Any]) -> dict[str, Any]:
    ordered = sorted(snapshots, key=lambda row: int(row.get("launch_age_seconds", 0)))
    by_age = {int(row.get("launch_age_seconds", 0)): row for row in ordered}
    features = _build_features(by_age)
    return {
        "launch_id": _first_present(*(row.get("launch_id") for row in ordered)),
        "token_mint": mint,
        "mint": mint,
        "launch_ts": _int_or_none(_first_present(*(row.get("launch_ts") for row in ordered))),
        "snapshot_ages": sorted(by_age),
        "features": features,
        "outcomes": _fdv_outcomes(ordered, outcome),
        "metadata_json": {
            "liquidity_proxy_source": _liquidity_source_for_launch(ordered),
            "available_snapshot_ages": sorted(by_age),
            "max_feature_snapshot_age_seconds": max((age for age in SNAPSHOT_AGES.values() if age in by_age), default=None),
        },
    }


def _build_features(by_age: dict[int, dict[str, Any]]) -> dict[str, Any]:
    liquidity = {age: _float_or_none((by_age.get(age) or {}).get("liquidity_proxy")) for age in SNAPSHOT_AGES.values()}
    features = {
        **{f"liquidity_proxy_{label}": liquidity[age] for label, age in SNAPSHOT_AGES.items()},
        "liquidity_proxy_retention_30s_to_10m": _ratio(liquidity[600], liquidity[30]),
        "liquidity_proxy_retention_30s_to_30m": _ratio(liquidity[1800], liquidity[30]),
        "liquidity_proxy_retention_3m_to_30m": _ratio(liquidity[1800], liquidity[180]),
        "liquidity_proxy_retention_10m_to_120m": _ratio(liquidity[7200], liquidity[600]),
        "liquidity_proxy_drop_30s_to_30m": _drop(liquidity[30], liquidity[1800]),
        "liquidity_proxy_drop_10m_to_120m": _drop(liquidity[600], liquidity[7200]),
        "liquidity_proxy_growth_30s_to_3m": _growth(liquidity[30], liquidity[180]),
        "liquidity_proxy_growth_3m_to_10m": _growth(liquidity[180], liquidity[600]),
        "liquidity_proxy_growth_10m_to_30m": _growth(liquidity[600], liquidity[1800]),
        "liquidity_proxy_growth_30m_to_120m": _growth(liquidity[1800], liquidity[7200]),
        "liquidity_proxy_slope_30s_to_30m": _slope(liquidity[30], liquidity[1800], 30, 1800),
    }
    snapshot_30m = by_age.get(1800)
    event_count = _field_value(snapshot_30m, "event_count")
    features.update(
        {
            "liquidity_per_active_wallet_30m": _ratio(liquidity[1800], _field_value(snapshot_30m, "active_wallets")),
            "liquidity_per_unique_actor_30m": _ratio(liquidity[1800], _field_value(snapshot_30m, "unique_actors")),
            "liquidity_per_event_30m": _ratio(liquidity[1800], event_count),
            "liquidity_per_buy_30m": _ratio(liquidity[1800], _field_value(snapshot_30m, "buy_count")),
            "liquidity_per_sell_30m": _ratio(liquidity[1800], _field_value(snapshot_30m, "sell_count")),
        }
    )
    return features


def _fdv_outcomes(snapshots: list[dict[str, Any]], outcome: dict[str, Any]) -> dict[str, Any]:
    valued = [
        row for row in snapshots
        if row.get("valuation_proxy_available") and _float_or_none(row.get("valuation_proxy_usd")) is not None
    ]
    values = [_float_or_none(row.get("valuation_proxy_usd")) for row in valued]
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
        "snapshot age / snapshot label": (snapshot_total, sum(1 for row in snapshots if row.get("launch_age_seconds") is not None)),
        "liquidity_proxy": (snapshot_total, sum(1 for row in snapshots if _float_or_none(row.get("liquidity_proxy")) is not None)),
        "bonding_curve_post_balance": (
            snapshot_total,
            sum(
                1 for row in snapshots
                if _float_or_none(row.get("bonding_curve_liquidity_proxy_sol")) is not None
                or (row.get("metadata_json") or {}).get("liquidity_proxy_source") == "bonding_curve_post_balance"
            ),
        ),
        "price/FDV proxy fields": (
            snapshot_total,
            sum(
                1 for row in snapshots
                if row.get("valuation_proxy_available") and _float_or_none(row.get("valuation_proxy_usd")) is not None
            ),
        ),
        "120m liquidity-proxy availability": (
            launch_total,
            sum(1 for row in launch_rows if row["outcomes"].get("liquidity_proxy_available_120m")),
        ),
        "120m price availability": (
            launch_total,
            sum(1 for row in launch_rows if row["outcomes"].get("price_available_120m")),
        ),
        "FDV-proxy runup": (
            launch_total,
            sum(1 for row in launch_rows if row["outcomes"].get("fdv_proxy_runup_120m") is not None),
        ),
        "FDV-proxy drawdown": (
            launch_total,
            sum(1 for row in launch_rows if row["outcomes"].get("fdv_proxy_drawdown_120m") is not None),
        ),
    }
    return {
        field: {
            "available_rows": available,
            "missing_rows": total - available,
            "coverage_pct": (available / total * 100) if total else 0,
            "denominator": total,
        }
        for field, (total, available) in checks.items()
    }


def _liquidity_proxy_semantics(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    sources = Counter(_liquidity_source(row) for row in snapshots)
    dominant = sources.most_common(1)[0][0] if sources else None
    return {
        "classification": "proxy",
        "dominant_source": dominant,
        "source_counts": dict(sorted(sources.items())),
        "exact_semantics": (
            "liquidity_proxy is treated as a bonding-curve reserve/balance proxy when "
            "source is bonding_curve_post_balance; it is not confirmed DEX order-book depth."
        ),
        "is_confirmed_dex_depth": False,
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
    summary.update({"bucket": f"q{bucket_number}", "feature_min": min(values) if values else None, "feature_max": max(values) if values else None})
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
    runups = [_float_or_none(row["outcomes"].get("fdv_proxy_runup_120m")) for row in rows]
    runups = sorted(value for value in runups if value is not None)
    liquidity_values = [_feature_value(row, "liquidity_proxy_30s") for row in rows]
    liquidity_values = sorted(value for value in liquidity_values if value is not None)
    runup_p99 = _quantile(runups, 0.99)
    liquidity_p99 = _quantile(liquidity_values, 0.99)
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
        "exclude_extreme_liquidity_proxy_values": _outcome_summary(
            [row for row in rows if liquidity_p99 is None or (_feature_value(row, "liquidity_proxy_30s") or 0) <= liquidity_p99]
        ),
    }


def _warning_flags(rows: list[dict[str, Any]], field_audit: dict[str, dict[str, Any]]) -> list[str]:
    warnings = ["not_confirmed_dex_depth", "true_market_cap_claims_blocked"]
    if field_audit["liquidity_proxy"]["missing_rows"]:
        warnings.append("liquidity_proxy_missing")
    if field_audit["FDV-proxy runup"]["missing_rows"] or field_audit["FDV-proxy drawdown"]["missing_rows"]:
        warnings.append("fdv_proxy_outcomes_missing")
    if not rows:
        warnings.append("empty_dataset")
    return warnings


def _classify(rows: list[dict[str, Any]], feature_reports: dict[str, dict[str, Any]], warning_flags: list[str]) -> str:
    if len(rows) < 100 or "fdv_proxy_outcomes_missing" in warning_flags:
        return "data_limited"
    primary = [
        feature_reports["liquidity_proxy_30s"],
        feature_reports["liquidity_proxy_retention_30s_to_30m"],
        feature_reports["liquidity_proxy_growth_30s_to_3m"],
        feature_reports["liquidity_per_active_wallet_30m"],
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
    if signals >= 2:
        return "descriptive_signal_present"
    if signals == 1:
        return "weak_signal"
    return "no_signal"


def _limitations(warning_flags: list[str]) -> list[str]:
    limitations = [
        "Liquidity proxy is not confirmed DEX order-book depth.",
        "FDV proxy is not true market cap because circulating supply is unavailable.",
        "This cycle is descriptive research only and does not produce trading rules.",
    ]
    if "liquidity_proxy_missing" in warning_flags:
        limitations.append("Some snapshots are missing liquidity_proxy values.")
    return limitations


def _next_recommendation(classification: str, warning_flags: list[str]) -> str:
    if "liquidity_proxy_missing" in warning_flags:
        return "repair liquidity-proxy coverage before rerunning T004"
    if classification in {"descriptive_signal_present", "weak_signal"}:
        return "compare liquidity-proxy signal against T002 participation proxies without changing thesis status"
    return "keep liquidity proxy as descriptive diagnostic and test next thesis family"


def _public_report(report: dict[str, Any]) -> dict[str, Any]:
    public = dict(report)
    public.pop("launch_rows", None)
    return public


def _markdown_summary(report: dict[str, Any]) -> str:
    lines = [
        "# T004 Liquidity Persistence / Depth Proxy",
        "",
        f"- Final classification: `{report['final_classification']}`",
        f"- Launch count: `{report['sample_counts']['launch_count']}`",
        f"- Warning flags: `{report['warning_flags']}`",
        f"- Liquidity proxy semantics: `{report['liquidity_proxy_semantics']['dominant_source']}`",
        "",
        "## Feature Coverage Audit",
        "",
        "| Field | Available Rows | Missing Rows | Coverage |",
        "|---|---:|---:|---:|",
    ]
    for field, audit in report["field_coverage_audit"].items():
        lines.append(f"| `{field}` | {audit['available_rows']} | {audit['missing_rows']} | {audit['coverage_pct']:.2f}% |")
    lines.extend(["", "## Median Outcome Tables", ""])
    for feature, feature_report in report["feature_reports"].items():
        lines.extend([f"### `{feature}`", "", "| Bucket | Samples | Feature Min | Feature Max | Median FDV Runup | Median FDV Drawdown | Price 120m | Liquidity 120m |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
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
    lines.extend(["## Limitations", "", *[f"- {item}" for item in report["limitations"]], "", "## Reproducible Command", "", "```bash", report["reproducible_command"], "```"])
    return "\n".join(lines) + "\n"


def _status_markdown(report: dict[str, Any], markdown_path: Path, json_path: Path) -> str:
    return "\n".join(
        [
            "# T004 Liquidity Persistence Status",
            "",
            "## Thesis Description",
            "",
            "Do launches with stronger early liquidity-proxy persistence and healthier liquidity trajectory have better FDV-proxy lifecycle outcomes?",
            "",
            "## Dataset Used",
            "",
            "- Strict launch-regime FDV-proxy lifecycle dataset",
            f"- Launches analyzed: `{report['sample_counts']['launch_count']}`",
            "",
            "## Liquidity Proxy Semantics",
            "",
            f"- Dominant source: `{report['liquidity_proxy_semantics']['dominant_source']}`",
            f"- Exact semantics: {report['liquidity_proxy_semantics']['exact_semantics']}",
            "- Confirmed DEX depth: `False`",
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
        "./trading_env/bin/python -m research.mtp_research.validation.run_liquidity_persistence_thesis "
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


def _liquidity_source_for_launch(rows: list[dict[str, Any]]) -> str | None:
    counts = Counter(_liquidity_source(row) for row in rows)
    return counts.most_common(1)[0][0] if counts else None


def _liquidity_source(row: dict[str, Any]) -> str:
    return str((row.get("metadata_json") or {}).get("liquidity_proxy_source") or row.get("valuation_source") or "unknown")


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _drop(start: float | None, end: float | None) -> float | None:
    if start in (None, 0) or end is None:
        return None
    return max(0.0, (start - end) / start)


def _growth(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return end - start


def _slope(start: float | None, end: float | None, start_age: int, end_age: int) -> float | None:
    growth = _growth(start, end)
    if growth is None or end_age == start_age:
        return None
    return growth / (end_age - start_age)


def _feature_value(row: dict[str, Any], feature: str) -> float | None:
    return _float_or_none(row["features"].get(feature))


def _distribution_summary(values: list[float]) -> dict[str, Any]:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None}
    return {"count": len(clean), "min": clean[0], "p25": _quantile(clean, 0.25), "median": median(clean), "p75": _quantile(clean, 0.75), "max": clean[-1], "mean": mean(clean)}


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
